import requests
from bs4 import BeautifulSoup
import argparse
import re
import csv
from collections import Counter
import time
import sys

# ANSI escape codes for bold
BOLD = '\033[1m'
RESET = '\033[0m'

# Set up argument parser
parser = argparse.ArgumentParser(description="Scrape lyrics from Genius and find matches.")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('-s', '--song', help="Full Genius song URL (e.g., 'https://genius.com/Future-the-way-things-going-lyrics')")
group.add_argument('-a', '--album', help="Full Genius album URL (e.g., 'https://genius.com/albums/Future/Hndrxx')")
group.add_argument('-artist', help="Full Genius artist albums URL (e.g., 'https://genius.com/artists/Future/albums')")
args = parser.parse_args()

# Function to generate plural form of a keyword
def pluralize(word):
    """Generate the plural form of a word based on simple rules."""
    if ' ' in word:  # Handle phrases (e.g., "rolls royce")
        parts = word.split()
        last_word = parts[-1]
        parts[-1] = pluralize(last_word)  # Pluralize only the last word
        return ' '.join(parts)
    
    if word.endswith(('s', 'x', 'z', 'ch', 'sh')):
        return word + 'es'
    elif word.endswith('y') and word[-2] not in 'aeiou':
        return word[:-1] + 'ies'
    else:
        return word + 's'

# Read keywords from keywords.txt and generate plurals
with open('keywords.txt', 'r') as file:
    keywords = [line.strip() for line in file if line.strip()]
    all_keywords = []
    for kw in keywords:
        all_keywords.append(kw)  # Original keyword
        all_keywords.append(pluralize(kw))  # Plural form

# Compile a single regex pattern for exact matches of singular and plural forms
pattern = re.compile(r'\b(' + '|'.join(map(re.escape, [kw.lower() for kw in all_keywords])) + r')\b')

def scrape_song(song_url):
    """Scrape lyrics, song title, artist, album, and matched keywords from a single song URL."""
    time.sleep(2)  # 2-second delay before request
    response = requests.get(song_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Get the song title from the first h1 element
    song_title = soup.find('h1')
    song_title_text = song_title.get_text(strip=True) if song_title else "Unknown Title"
    
    # Get the artist name from the display text of the first link with /artists/
    artist_link = soup.find('a', href=re.compile('/artists/'))
    artist_name = artist_link.get_text(strip=True) if artist_link else "Unknown Artist"
    
    # Get the album name from the display text of the link with href="#primary-album"
    album_link = soup.find('a', href="#primary-album")
    album_name = album_link.get_text(strip=True) if album_link else "Unknown Album"
    
    lyrics_containers = soup.find_all('div', {'data-lyrics-container': 'true'})
    text_content = ''
    for container in lyrics_containers:
        text_content += container.get_text(separator='\n') + '\n'
    
    lines = text_content.splitlines()
    matches = {}
    matched_keywords = set()  # Track unique matched keywords
    for line in lines:
        line_lower = line.lower()
        found = pattern.findall(line_lower)
        if found:
            if line not in matches:  # Only add if line isn’t already present
                matches[line] = set()  # Use a set to avoid duplicate keywords
            matches[line].update(found)
            matched_keywords.update(found)  # Add found keywords to the set
    
    return song_title_text, matches, matched_keywords, artist_name, album_name

def scrape_album(album_url):
    """Scrape lyrics from all songs linked on an album page, get album title and artist."""
    time.sleep(2)  # 2-second delay before album request
    response = requests.get(album_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Get the album title from the first h1 element
    album_title = soup.find('h1')
    album_title_text = soup.find('h1').get_text(strip=True) if album_title else "Unknown Album"
    
    # Get the artist name from the first h2 element and normalize for URL matching
    artist = soup.find('h2')
    artist_name = artist.get_text(strip=True) if artist else "Unknown Artist"
    artist_url_part = artist_name.lower().replace(' ', '-')  # e.g., "Yo Gotti" -> "yo-gotti"
    
    # Find song URLs containing the artist name and ending with -lyrics
    song_links = soup.select('a[href]')
    song_urls = {link['href'] if link['href'].startswith('http') else f"https://genius.com{link['href']}" 
                 for link in song_links if link['href'].endswith('-lyrics') and artist_url_part in link['href'].lower()}
    
    print(f"\n{BOLD}Found song links:{RESET}")
    total_songs = len(song_urls)
    for url in song_urls:
        print(url)
    print("")
    
    all_matches = {}
    all_matched_keywords = set()  # Track matched keywords across all songs
    current_song = 0
    for url in song_urls:
        current_song += 1
        print(f"👀 {BOLD}Scraping song ({current_song}/{total_songs}):{RESET} {url}", end='', flush=True)
        try:
            song_title, song_matches, matched_keywords, _, _ = scrape_song(url)  # Ignore song-level artist and album
            print(f"\r✅ {BOLD}Scraping song ({current_song}/{total_songs}):{RESET} {url}")
            if song_matches:
                all_matches[song_title] = song_matches
                all_matched_keywords.update(matched_keywords)  # Aggregate matched keywords
        except requests.RequestException as e:
            print(f"\r{BOLD}Scraping song ({current_song}/{total_songs}):{RESET} {url} (Failed: {e})")
    
    return artist_name, album_title_text, all_matches, all_matched_keywords

def scrape_artist_albums(artist_url):
    """Scrape all albums and their songs from an artist's albums page."""
    time.sleep(2)  # 2-second delay before artist page request
    response = requests.get(artist_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Get all links with /albums/ in the URL
    album_links = soup.select('a[href*="/albums/"]')
    unique_album_urls = {link['href'] if link['href'].startswith('http') else f"https://genius.com{link['href']}" 
                         for link in album_links if '/albums/' in link['href']}
    
    print(f"\n{BOLD}Found album links:{RESET}")
    for url in unique_album_urls:
        print(url)
    print("")
    
    all_albums_matches = {}
    all_matched_keywords = set()  # Track matched keywords across all albums
    for album_url in unique_album_urls:
        print(f"{BOLD}\nScraping album:{RESET} {album_url}")
        try:
            artist_name, album_title, album_matches, album_matched_keywords = scrape_album(album_url)  # Delay inside scrape_album
            if album_matches:
                all_albums_matches[album_title] = (artist_name, album_matches)
                all_matched_keywords.update(album_matched_keywords)
        except requests.RequestException as e:
            print(f"Failed to scrape {album_url}: {e}")
    
    return all_albums_matches, all_matched_keywords

# Function to write results to CSV
def write_to_csv(results):
    # Count keyword frequencies
    keyword_counts = Counter(result['Keyword'] for result in results)
    
    # Sort results by frequency (descending) and then by keyword alphabetically
    sorted_results = sorted(results, key=lambda x: (-keyword_counts[x['Keyword']], x['Keyword']))
    
    with open('lyrics_matches.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Keyword', 'Lyrics', 'Song', 'Album', 'Artist']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for result in sorted_results:
            writer.writerow(result)

# Function to write match results to output.txt
def write_matches_to_txt(output_lines):
    with open('output.txt', 'w', encoding='utf-8') as txtfile:
        txtfile.write('\n'.join(output_lines))

# Choose path based on argument
results = []  # List to store all results for CSV
output_lines = []  # List to store match lines for output.txt
if args.song:
    print(f"{BOLD}\nScraping song:{RESET} {args.song}")
    song_title, matches, matched_keywords, artist_name, album_name = scrape_song(args.song)
    if matches:
        max_keyword_length = max(len(kw) for kw in matched_keywords) if matched_keywords else 0
        print(f"\n{BOLD}{song_title}{RESET}")
        output_lines.append(f"{song_title}")
        for line, found_keywords in matches.items():
            for keyword in found_keywords:
                bolded_line = re.sub(rf'\b{re.escape(keyword)}\b', f'{BOLD}{keyword}{RESET}', line, flags=re.IGNORECASE)
                match_line = f"- {keyword:<{max_keyword_length}}   {bolded_line}"
                print(match_line)
                output_lines.append(match_line.replace(BOLD, '').replace(RESET, ''))  # Remove ANSI codes for text file
                results.append({
                    'Keyword': keyword,
                    'Lyrics': line,
                    'Song': song_title,
                    'Album': album_name,
                    'Artist': artist_name
                })
    else:
        print(f"\n{BOLD}{song_title}{RESET}")
        print("No matches found for any keywords.")
elif args.album:
    print(f"{BOLD}\nScraping album:{RESET} {args.album}")
    artist_name, album_title, all_matches, all_matched_keywords = scrape_album(args.album)
    if all_matches:
        max_keyword_length = max(len(kw) for kw in all_matched_keywords) if all_matched_keywords else 0
        print(f"\n{BOLD}Artist:{RESET} {artist_name}")
        print(f"{BOLD}Album:{RESET} {album_title}")
        output_lines.append(f"Artist: {artist_name}")
        output_lines.append(f"Album: {album_title}")
        for song_title, matches in all_matches.items():
            print(f"\n{BOLD}{song_title}{RESET}")
            output_lines.append(f"\n{song_title}")
            for line, found_keywords in matches.items():
                for keyword in found_keywords:
                    bolded_line = re.sub(rf'\b{re.escape(keyword)}\b', f'{BOLD}{keyword}{RESET}', line, flags=re.IGNORECASE)
                    match_line = f"- {keyword:<{max_keyword_length}}   {bolded_line}"
                    print(match_line)
                    output_lines.append(match_line.replace(BOLD, '').replace(RESET, ''))  # Remove ANSI codes for text file
                    results.append({
                        'Keyword': keyword,
                        'Lyrics': line,
                        'Song': song_title,
                        'Album': album_title,
                        'Artist': artist_name
                    })
    else:
        print(f"\n{BOLD}Artist:{RESET} {artist_name}")
        print(f"{BOLD}Album:{RESET} {album_title}")
        print("No matches found in any songs from the album.")
elif args.artist:
    print(f"{BOLD}\nScraping artist albums:{RESET} {args.artist}")
    all_albums_matches, all_matched_keywords = scrape_artist_albums(args.artist)
    if all_albums_matches:
        max_keyword_length = max(len(kw) for kw in all_matched_keywords) if all_matched_keywords else 0
        for album_title, (artist_name, matches) in all_albums_matches.items():
            print(f"\n{BOLD}Artist:{RESET} {artist_name}")
            print(f"{BOLD}Album:{RESET} {album_title}")
            output_lines.append(f"Artist: {artist_name}")
            output_lines.append(f"Album: {album_title}")
            for song_title, song_matches in matches.items():
                print(f"\n{BOLD}{song_title}{RESET}")
                output_lines.append(f"\n{song_title}")
                for line, found_keywords in song_matches.items():
                    for keyword in found_keywords:
                        bolded_line = re.sub(rf'\b{re.escape(keyword)}\b', f'{BOLD}{keyword}{RESET}', line, flags=re.IGNORECASE)
                        match_line = f"- {keyword:<{max_keyword_length}}   {bolded_line}"
                        print(match_line)
                        output_lines.append(match_line.replace(BOLD, '').replace(RESET, ''))  # Remove ANSI codes for text file
                        results.append({
                            'Keyword': keyword,
                            'Lyrics': line,
                            'Song': song_title,
                            'Album': album_title,
                            'Artist': artist_name
                        })
    else:
        print("\nNo matches found in any albums.")

# Write results to CSV and output.txt if there are any
if results:
    write_to_csv(results)
    write_matches_to_txt(output_lines)
    print(f"\nResults exported to 'lyrics_matches.csv' and 'output.txt'")