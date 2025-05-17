# arXiv3r bot.py

import os
import re
import discord
import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Regex stuffs
OLD_STYLE_PATTERN = r'\[([\w-]+\/\d{7})\]'  # [cat/nnnn]
NEW_STYLE_PATTERN = r'\[(\d{4}\.\d{4,5}(?:v\d+)?)\]' 

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
                    return {
                        'title': title,
                        'authors': authors,
                        'abstract': abstract,
                        'link': link
                    }

                else:
                    print(f"Error: API returned status code {response.status}")
                    return None

        except Exception as e:
            print(f"Error fetching arXiv paper {arxiv_id}: {e}")
            return None


@bot.event
async def on_ready():
    """Called when arXiv3r is functional"""
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print(f'Bot is active in {len(bot.guilds)} servers')
    
    # Set bot status
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="for [arXiv:IDs]"
    ))

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
    
    found_ids = list(set(old_style_ids + new_style_ids))
    if not found_ids:
        await bot.process_commands(message)
        return
    


    for arxiv_id in found_ids:
        try:
            

            async with message.channel.typing():
                await asyncio.sleep(1)
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
            print(f"Error processing arXiv ID {arxiv_id}: {e}")
    await bot.process_commands(message)


@bot.command(name='00arXiv3r', description='Shows help information for arXiv3r bot')
async def help_command(ctx):
    """Shows help information for arXiv3r bot."""
    help_text = (
        "**arXiv3r Bot Help**\n\n"
        "arXiv3r detects arXiv identifiers in square brackets of the format [yymm.nnnn] or [cat/nnnnn] "
        "and converts them to formatted links with titles. [v1]\n\n"
        "[v1] Init commit."
        "[v2] PDF linking and options for version history/metadata."
    )
    await ctx.send(help_text)


# THe
if __name__ == "__main__":
    bot.run(TOKEN)
