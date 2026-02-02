# coding:utf-8

import os
import datetime
import requests
import urllib.parse
from pyquery import PyQuery as pq
import logging
import time

def setup_logger():
    """Initialize logger with monthly log file and console output"""
    # Create log directory if it doesn't exist
    os.makedirs('log', exist_ok=True)

    # Generate monthly log filename
    log_filename = f"log/{datetime.datetime.now().strftime('%Y-%m')}.log"

    # Create logger
    logger = logging.getLogger('github_trending_scraper')
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    # File handler - append mode, UTF-8 encoding
    file_handler = logging.FileHandler(log_filename, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Console handler - for real-time monitoring
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Format: [2026-02-02 02:00:15] INFO - Message
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

def scrape_url(url, logger):
    ''' Scrape github trending url
    '''
    HEADERS = {
        'User-Agent'		: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.7; rv:11.0) Gecko/20100101 Firefox/11.0',
        'Accept'			: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding'	: 'gzip,deflate,sdch',
        'Accept-Language'	: 'zh-CN,zh;q=0.8'
    }

    logger.debug(f"Requesting: {url}")

    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        logger.info(f"HTTP {r.status_code} - {url}")

        if r.status_code != 200:
            logger.error(f"HTTP request failed with status {r.status_code}")
            raise Exception(f"HTTP {r.status_code}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {str(e)}")
        raise

    d = pq(r.content)
    items = d('div.Box article.Box-row')

    results = {}
    # codecs to solve the problem utf-8 codec like chinese
    for item in items:
        i = pq(item)
        title = i(".lh-condensed a").text()
        description = i("p.col-9").text()
        url = i(".lh-condensed a").attr("href")
        url = "https://github.com" + url
        results[title] = { 'title': title, 'url': url, 'description': description }

    logger.debug(f"Parsed {len(results)} items from HTML")
    return results

def scrape_lang(language, logger):
    ''' Scrape github trending with lang parameters
    '''
    lang_display = language if language else 'All language'
    logger.info(f"[{lang_display}] Starting scrape")

    url = 'https://github.com/trending/{language}'.format(language=urllib.parse.quote_plus(language))
    r1 = scrape_url(url, logger)

    url = 'https://github.com/trending/{language}?spoken_language_code=zh'.format(language=urllib.parse.quote_plus(language))
    r2 = scrape_url(url, logger)

    result = { **r1, **r2 }
    logger.info(f"[{lang_display}] Merged {len(result)} unique items from both sources")
    return result

def write_markdown(lang, results, archived_contents, logger):
    ''' Write the results to markdown file
    '''
    content = ''
    with open('README.md', mode='r', encoding='utf-8') as f:
        content = f.read()
    content = convert_file_contenet(content, lang, results, archived_contents, logger)
    with open('README.md', mode='w', encoding='utf-8') as f:
        f.write(content)

def is_title_exist(title, content, archived_contents):
    if '[' + title + ']' in content:
        return True
    for archived_content in archived_contents:
        if '[' + title + ']' in archived_content:
            return True
    return False

def convert_file_contenet(content, lang, results, archived_contents, logger):
    ''' Add distinct results to content
    '''
    distinct_results = []
    for title, result in results.items():
        if not is_title_exist(title, content, archived_contents):
            distinct_results.append(result)

    lang_display = lang if lang else 'All language'

    if not distinct_results:
        logger.info(f'[{lang_display}] No new distinct results (all duplicates)')
        return content

    lang_title = convert_lang_title(lang)
    if lang_title not in content:
        content = content + lang_title + '\n\n'

    logger.info(f'[{lang_display}] Added {len(distinct_results)} new items to README.md')
    return content.replace(lang_title + '\n\n', lang_title + '\n\n' + convert_result_content(distinct_results))

def convert_result_content(results):
    ''' Format all results to a string
    '''
    strdate = datetime.datetime.now().strftime('%Y-%m-%d')
    content = ''
    for result in results:
        content = content + u"* 【{strdate}】[{title}]({url}) - {description}\n".format(
            strdate=strdate, title=result['title'], url=result['url'],
            description=format_description(result['description']))
    return content

def format_description(description):
    ''' Remove new line characters
    '''
    if not description:
        return ''
    return description.replace('\r', '').replace('\n', '')

def convert_lang_title(lang):
    ''' Lang title
    '''
    if lang == '':
        return '## All language'
    return '## ' + lang.capitalize()

def get_archived_contents(logger):
    archived_contents = []
    archived_files = os.listdir('./archived')
    for file in archived_files:
        content = ''
        with open('./archived/' + file, mode='r', encoding='utf-8') as f:
            content = f.read()
        archived_contents.append(content)
    logger.info(f"Loaded {len(archived_files)} archived files for deduplication")
    return archived_contents

def job():
    ''' Main scraper job with logging and error handling
    '''
    # Initialize logger
    logger = setup_logger()
    start_time = time.time()

    logger.info("="*60)
    logger.info("GitHub Trending Scraper - Job Started")
    logger.info("="*60)

    # Get archived contents
    archived_contents = get_archived_contents(logger)

    # Tracking metrics
    total_scraped = 0
    total_new = 0
    error_count = 0

    # Start the scrape job
    languages = ['', 'python', 'jupyter-notebook','typescript', 'javascript', 'rust',  'java','go', 'c', 'c++', 'c#', 'html','shell', 'css', 'unknown']

    for lang in languages:
        try:
            # Scrape language
            results = scrape_lang(lang, logger)
            total_scraped += len(results)

            # Write to markdown (logs internally how many new items added)
            write_markdown(lang, results, archived_contents, logger)

            # Small delay to avoid rate limiting
            time.sleep(2)

        except Exception as e:
            error_count += 1
            lang_display = lang if lang else 'All language'
            logger.error(f"[{lang_display}] Failed to process: {str(e)}", exc_info=True)
            continue

    # Calculate execution time
    elapsed = time.time() - start_time

    # Log summary
    logger.info("="*60)
    logger.info("Job Summary:")
    logger.info(f"  Languages processed: {len(languages)}")
    logger.info(f"  Total items scraped: {total_scraped}")
    logger.info(f"  Errors encountered: {error_count}")
    logger.info(f"  Execution time: {elapsed:.2f} seconds")
    logger.info("="*60)

if __name__ == '__main__':
    job()