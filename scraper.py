# coding:utf-8

import os
import datetime
import re
import requests
import urllib.parse
from pyquery import PyQuery as pq
import logging
import time
from dateutil.relativedelta import relativedelta

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

def parse_entry_date(line):
    """从条目行中解析日期

    输入: "* 【2026-01-30】[项目名](URL) - 描述"
    输出: datetime.date(2026, 1, 30)
    """
    match = re.search(r'【(\d{4}-\d{2}-\d{2})】', line)
    if match:
        date_str = match.group(1)
        return datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    return None

def find_months_to_archive():
    """查找从最新归档月份到上个月之间所有需要归档的月份

    返回: ['2025-11', '2025-12', '2026-01'] 形式的列表
    """
    # 获取已归档的月份
    archived_files = os.listdir('./archived')
    archived_months = []
    for f in archived_files:
        if f.endswith('.md'):
            month_str = f.replace('.md', '')  # '2025-10'
            archived_months.append(month_str)

    if not archived_months:
        return []  # 没有归档文件，跳过

    archived_months.sort()
    latest_archived = archived_months[-1]

    # 计算上个月
    today = datetime.datetime.now()
    last_month = today - relativedelta(months=1)
    last_month_str = last_month.strftime('%Y-%m')

    # 生成需要归档的月份列表
    months_to_archive = []
    current = datetime.datetime.strptime(latest_archived, '%Y-%m') + relativedelta(months=1)
    end = datetime.datetime.strptime(last_month_str, '%Y-%m')

    while current <= end:
        months_to_archive.append(current.strftime('%Y-%m'))
        current += relativedelta(months=1)

    return months_to_archive

def extract_entries_by_month(content, target_month):
    """从 README.md 内容中提取指定月份的所有条目

    返回: {'All language': ['* 【2025-11-30】...', ...], 'Python': [...], ...}
    """
    entries_by_lang = {}
    current_lang = None

    for line in content.split('\n'):
        # 检测语言分类标题
        if line.startswith('## '):
            current_lang = line[3:].strip()
            continue

        # 检测条目行
        if line.startswith('* 【') and current_lang:
            entry_date = parse_entry_date(line)
            if entry_date:
                entry_month = entry_date.strftime('%Y-%m')
                if entry_month == target_month:
                    if current_lang not in entries_by_lang:
                        entries_by_lang[current_lang] = []
                    entries_by_lang[current_lang].append(line)

    return entries_by_lang

def write_archive_file(month, entries_by_lang, logger):
    """将指定月份的条目写入归档文件"""
    if not entries_by_lang:
        logger.info(f"[Archive] No entries for {month}, skipping")
        return

    filepath = f'./archived/{month}.md'

    # 按照 README.md 中的语言顺序组织内容
    lang_order = ['All language', 'Java', 'Python', 'Javascript', 'Typescript',
                  'Go', 'C', 'C++', 'C#', 'Html', 'Css', 'Rust',
                  'Jupyter-notebook', 'Shell', 'Unknown']

    content_lines = []
    processed_langs = set()

    for lang in lang_order:
        if lang in entries_by_lang:
            content_lines.append(f'## {lang}')
            content_lines.append('')
            # 按日期倒序排列(最新的在前)
            sorted_entries = sorted(entries_by_lang[lang],
                                   key=lambda x: parse_entry_date(x) or datetime.date.min,
                                   reverse=True)
            content_lines.extend(sorted_entries)
            content_lines.append('')
            processed_langs.add(lang)

    # 处理未在 lang_order 中的语言
    for lang, entries in entries_by_lang.items():
        if lang not in processed_langs:
            content_lines.append(f'## {lang}')
            content_lines.append('')
            sorted_entries = sorted(entries,
                                   key=lambda x: parse_entry_date(x) or datetime.date.min,
                                   reverse=True)
            content_lines.extend(sorted_entries)
            content_lines.append('')

    content = '\n'.join(content_lines)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    total_entries = sum(len(v) for v in entries_by_lang.values())
    logger.info(f"[Archive] Created {filepath} with {total_entries} entries")

def cleanup_readme(content, days_to_keep, logger):
    """清理 README.md 中超过指定天数的条目"""
    cutoff_date = datetime.datetime.now().date() - datetime.timedelta(days=days_to_keep)

    new_lines = []
    removed_count = 0
    kept_count = 0

    for line in content.split('\n'):
        # 处理条目行
        if line.startswith('* 【'):
            entry_date = parse_entry_date(line)
            if entry_date and entry_date < cutoff_date:
                removed_count += 1
                continue  # 跳过超期条目
            kept_count += 1

        new_lines.append(line)

    logger.info(f"[Cleanup] Removed {removed_count} old entries (before {cutoff_date}), kept {kept_count}")

    return '\n'.join(new_lines)

def archive_old_entries(logger):
    """主归档入口函数，在 job() 开始时调用"""
    logger.info("="*60)
    logger.info("Archive Check - Started")
    logger.info("="*60)

    # 1. 查找需要归档的月份
    months_to_archive = find_months_to_archive()

    if not months_to_archive:
        logger.info("[Archive] No months need to be archived")
    else:
        logger.info(f"[Archive] Months to archive: {months_to_archive}")

        # 2. 读取 README.md
        with open('README.md', 'r', encoding='utf-8') as f:
            readme_content = f.read()

        # 3. 对每个月份进行归档
        for month in months_to_archive:
            entries = extract_entries_by_month(readme_content, month)
            write_archive_file(month, entries, logger)

    # 4. 清理超过60天的数据
    with open('README.md', 'r', encoding='utf-8') as f:
        readme_content = f.read()

    cleaned_content = cleanup_readme(readme_content, days_to_keep=60, logger=logger)

    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(cleaned_content)

    logger.info("="*60)
    logger.info("Archive Check - Completed")
    logger.info("="*60)

def job():
    ''' Main scraper job with logging and error handling
    '''
    # Initialize logger
    logger = setup_logger()
    start_time = time.time()

    logger.info("="*60)
    logger.info("GitHub Trending Scraper - Job Started")
    logger.info("="*60)

    # Archive old entries before scraping
    archive_old_entries(logger)

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