# arXiv3r bot.py

import os
import re
import discord
import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("arXiv3r.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("arXiv3r.bot")

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    logger.error("DISCORD_BOT_TOKEN not found! Please set this environment variable.")
    
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Regex stuffs
OLD_STYLE_PATTERN = r'\[([\w-]+\/\d{7})\]'  # [cat/nnnn]
NEW_STYLE_PATTERN = r'\[(\d{4}\.\d{4,5}(?:v\d+)?)\]' 
BIBTEX_PATTERN = r'\[bib:(\d{4}\.\d{4,5}(?:v\d+)?|[\w-]+\/\d{7})\]'  # [bib:ARXIV_ID]
AUTHOR_PATTERN = r'\[au:(.*?)\]'  # [au:AUTHOR_NAME]

# Store author subscriptions: {guild_id: {channel_id: {author_name: [user_ids]}}}
author_subscriptions = {}

async def fetch_paper_details(arxiv_id):
    """Use arXiv API"""
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    # Parse XML response
                    xml_data = await response.text()
                    root = ET.fromstring(xml_data)

                    namespaces = {
                        'atom': 'http://www.w3.org/2005/Atom',
                        'arxiv': 'http://arxiv.org/schemas/atom'
                    }
                    
                    # Extract paper details
                    entry = root.find('.//atom:entry', namespaces)
                    if entry is None:
                        return None




                    title_elem = entry.find('./atom:title', namespaces)
                    title = title_elem.text.replace('\n', ' ').strip() if title_elem is not None else "No title available"
                    author_elems = entry.findall('./atom:author/atom:name', namespaces)
                    authors = ', '.join([author.text for author in author_elems]) if author_elems else "Did you search for a real paper?"
                    

                    summary_elem = entry.find('./atom:summary', namespaces)
                    abstract = summary_elem.text.replace('\n', ' ').strip() if summary_elem is not None else "Don't spam the Discord channel like an idiot if not"
                    

                    link_elem = entry.find('./atom:link[@title="pdf"]', namespaces)
                    link = link_elem.get('href') if link_elem is not None else f"https://arxiv.org/abs/{arxiv_id}"
                    
                    # Get publication date for bibtex
                    published_elem = entry.find('./atom:published', namespaces)
                    published_date = published_elem.text[:10] if published_elem is not None else datetime.now().strftime("%Y-%m-%d")
                    
                    return {
                        'title': title,
                        'authors': authors,
                        'author_list': [author.text for author in author_elems],
                        'abstract': abstract,
                        'link': link,
                        'published_date': published_date
                    }

                else:
                    logger.error(f"Error: API returned status code {response.status}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching arXiv paper {arxiv_id}: {e}")
            return None

async def generate_bibtex(arxiv_id, paper_details):
    """Generate BibTeX citation for an arXiv paper"""
    if not paper_details:
        return f"Could not generate BibTeX for {arxiv_id} - paper details not found"
    
    # Format authors for BibTeX
    authors = paper_details['authors'].replace(', ', ' and ')
    
    # Extract year from published date
    year = paper_details['published_date'].split('-')[0]
    
    # Create BibTeX entry
    bibtex = (
        f"@article{{{arxiv_id.replace('/', '_').replace('.', '_')},\n"
        f"  author = {{{authors}}},\n"
        f"  title = {{{paper_details['title']}}},\n"
        f"  journal = {{arXiv preprint arXiv:{arxiv_id}}},\n"
        f"  year = {{{year}}},\n"
        f"  url = {{https://arxiv.org/abs/{arxiv_id}}}\n"
        f"}}"
    )
    
    return f"```bibtex\n{bibtex}\n```"

async def search_author_papers(author_name):
    """Search for recent papers by an author"""
    # Create a date range for the last 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    # Format the query
    query = f"au:\"{author_name}\" AND submittedDate:[{start_date.strftime('%Y%m%d')}* TO {end_date.strftime('%Y%m%d')}*]"
    encoded_query = query.replace(' ', '+')
    
    url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&sortBy=submittedDate&sortOrder=descending&max_results=5"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    xml_data = await response.text()
                    root = ET.fromstring(xml_data)
                    
                    namespaces = {
                        'atom': 'http://www.w3.org/2005/Atom',
                        'arxiv': 'http://arxiv.org/schemas/atom'
                    }
                    
                    entries = root.findall('.//atom:entry', namespaces)
                    results = []
                    
                    for entry in entries:
                        # Get arXiv ID from the ID URL
                        id_elem = entry.find('./atom:id', namespaces)
                        if id_elem is not None:
                            arxiv_url = id_elem.text
                            arxiv_id = arxiv_url.split('/')[-1]
                            
                            title_elem = entry.find('./atom:title', namespaces)
                            title = title_elem.text.replace('\n', ' ').strip() if title_elem is not None else "Title unavailable"
                            
                            published_elem = entry.find('./atom:published', namespaces)
                            published = published_elem.text if published_elem is not None else ""
                            
                            results.append({
                                'arxiv_id': arxiv_id,
                                'title': title,
                                'published': published[:10] if published else ""
                            })
                    
                    return results
                else:
                    logger.error(f"Error searching for author papers: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error searching for {author_name}'s papers: {e}")
            return []

@bot.event
async def on_ready():
    """Called when arXiv3r is functional"""
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    logger.info(f'Bot is active in {len(bot.guilds)} servers')
    
    # Set bot status
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="for [arXiv:IDs]"
    ))
    
    # Start author paper check loop
    bot.loop.create_task(check_author_papers())

# Claude help
# Wait old identifiers don't seem to work wtf.

@bot.event
async def on_message(message):
    """Process messages for arXiv identifiers."""


    if message.author.bot:
        return
    content = message.content

    old_style_ids = re.findall(OLD_STYLE_PATTERN, content)
    new_style_ids = re.findall(NEW_STYLE_PATTERN, content)
    bibtex_ids = re.findall(BIBTEX_PATTERN, content)
    author_matches = re.findall(AUTHOR_PATTERN, content)
    
    found_ids = list(set(old_style_ids + new_style_ids))
    
    # Process author subscriptions
    if author_matches:
        await process_author_subscriptions(message, author_matches)
    
    # Process regular arXiv IDs
    if found_ids:
        try:
            async with message.channel.typing():
                for arxiv_id in found_ids:
                    paper_details = await fetch_paper_details(arxiv_id)
                    if not paper_details:
                        continue
                    
                    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
                    abstract = paper_details['abstract']
                    if len(abstract) > 150:
                        abstract = abstract[:150] + '...'
                    
                    response = f"**{paper_details['title']}**"
                    response += f" | Authors: {paper_details['authors']}\n"
                    response += f"Link: {arxiv_url}"
                    response += f" | PDF: https://arxiv.org/pdf/{arxiv_id}\n"
                    response += f"Abs: {abstract}\n"
                    
                    await message.channel.send(response)
        
        except Exception as e:
            logger.error(f"Error processing arXiv ID {arxiv_id}: {e}")
    
    # Process BibTeX requests
    if bibtex_ids:
        try:
            async with message.channel.typing():
                for bibtex_id in bibtex_ids:
                    paper_details = await fetch_paper_details(bibtex_id)
                    if not paper_details:
                        continue
                    
                    bibtex = await generate_bibtex(bibtex_id, paper_details)
                    await message.channel.send(f"BibTeX citation for arXiv:{bibtex_id}\n{bibtex}")
        
        except Exception as e:
            logger.error(f"Error processing BibTeX request for {bibtex_id}: {e}")
    
    await bot.process_commands(message)

async def process_author_subscriptions(message, author_matches):
    """Process author subscription requests"""
    guild_id = str(message.guild.id) if message.guild else "DM"
    channel_id = str(message.channel.id)
    
    # Initialize nested dictionary structure if needed
    if guild_id not in author_subscriptions:
        author_subscriptions[guild_id] = {}
    if channel_id not in author_subscriptions[guild_id]:
        author_subscriptions[guild_id][channel_id] = {}
    
    for author_name in author_matches:
        author_name = author_name.strip()
        if author_name:
            # Add the subscription
            if author_name not in author_subscriptions[guild_id][channel_id]:
                author_subscriptions[guild_id][channel_id][author_name] = []
            
            user_id = str(message.author.id)
            if user_id not in author_subscriptions[guild_id][channel_id][author_name]:
                author_subscriptions[guild_id][channel_id][author_name].append(user_id)
                
                await message.channel.send(
                    f"{message.author.mention} You're now subscribed to new papers by {author_name}. "
                    f"You'll be notified in this channel when they publish."
                )

async def check_author_papers():
    """Periodically check for new papers by subscribed authors"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            for guild_id, channels in author_subscriptions.items():
                for channel_id, authors in channels.items():
                    for author_name, user_ids in authors.items():
                        if not user_ids:  # Skip if no subscribers
                            continue
                            
                        recent_papers = await search_author_papers(author_name)
                        
                        if recent_papers:
                            # Get the channel
                            if guild_id == "DM":
                                continue  # Skip DMs for simplicity
                            
                            channel = bot.get_channel(int(channel_id))
                            if not channel:
                                continue
                            
                            # Build notification message
                            notification = f"**New paper(s) by {author_name}!**\n"
                            notification += f"Notifying: {', '.join([f'<@{user_id}>' for user_id in user_ids])}\n\n"
                            
                            for paper in recent_papers:
                                notification += (
                                    f"• [{paper['arxiv_id']}] **{paper['title']}** (Published: {paper['published']})\n"
                                    f"  Link: https://arxiv.org/abs/{paper['arxiv_id']}\n\n"
                                )
                            
                            await channel.send(notification)
                            
                            # Clear subscribers after notification
                            author_subscriptions[guild_id][channel_id][author_name] = []
                        
        except Exception as e:
            logger.error(f"Error in author paper check: {e}")
        
        # Check once a day
        await asyncio.sleep(86400)  # 24 hours in seconds


@bot.command(name='00arXiv3r', description='Shows help information for arXiv3r bot')
async def help_command(ctx):
    """Shows help information for arXiv3r bot."""
    help_text = (
        "**arXiv3r**\n\n"
        "arXiv3r is a friendly app that detects arXiv identifiers [yymm.nnnn] or [cat/nnnnn] "
        "and converts them to formatted links with titles. [v2]\n\n"
        "**Commands:**\n"
        "• Use `[yymm.nnnn]` or `[cat/nnnnn]` to get paper details\n"
        "• Use `[bib:yymm.nnnn]` to get a BibTeX citation\n"
        "• Use `[au:Author Name]` to subscribe to new papers by an author\n\n"
        "• Go watch Dune Part 1 and Dune Part 2.\n"
        "[v1] Init commit.\n"
        "[v2] PDF linking, bibtex, multiple requests in single instance and author subscription.\n"
        "[v3] See github.com/vkalvakotamath/arXiv3r for upcoming releases. Suggestions are welcome!"
    )
    await ctx.send(help_text)


# Implement heartbeat mechanism to keep the bot alive
async def heartbeat():
    """Send a heartbeat message to keep the connection alive"""
    logger.info("Starting heartbeat mechanism")
    while True:
        try:
            logger.debug("Heartbeat pulse")
            await asyncio.sleep(300)  # Send heartbeat every 5 minutes
        except Exception as e:
            logger.error(f"Error in heartbeat: {e}")
            await asyncio.sleep(60)  # Wait a bit before retrying

# Start the heartbeat when the bot is ready
@bot.event
async def on_ready():
    """Called when arXiv3r is functional"""
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    logger.info(f'Bot is active in {len(bot.guilds)} servers')
    
    # Set bot status
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="for [arXiv:IDs]"
    ))
    
    # Start author paper check loop
    bot.loop.create_task(check_author_papers())
    
    # Start heartbeat mechanism
    bot.loop.create_task(heartbeat())

# THe
if __name__ == "__main__":
    try:
        logger.info("Starting arXiv3r")
        bot.run(TOKEN)
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
