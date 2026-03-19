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
from collections import defaultdict

LANG_ORDER = ['All language', 'Java', 'Python', 'Javascript', 'Typescript',
              'Go', 'C', 'C++', 'C#', 'Html', 'Css', 'Rust',
              'Jupyter-notebook', 'Shell', 'Unknown']

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
    ''' Add distinct results to content (date-first format)
    '''
    distinct_results = []
    for title, result in results.items():
        if not is_title_exist(title, content, archived_contents):
            distinct_results.append(result)

    lang_display = lang if lang else 'All language'

    if not distinct_results:
        logger.info(f'[{lang_display}] No new distinct results (all duplicates)')
        return content

    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    date_title = f'## {today_str}'
    lang_title = convert_readme_lang_title(lang)

    lines = content.split('\n')

    # 确保日期段落存在
    if date_title not in [l.strip() for l in lines]:
        lines = insert_date_section(lines, date_title)

    # 确保语言子标题存在于日期段落内
    if not has_lang_under_date(lines, date_title, lang_title):
        lines = insert_lang_under_date(lines, date_title, lang_title, lang)

    # 在语言子标题后插入条目
    entry_text = convert_result_content(distinct_results)
    lines = insert_entries_after_lang(lines, date_title, lang_title, entry_text)

    logger.info(f'[{lang_display}] Added {len(distinct_results)} new items to README.md')
    return '\n'.join(lines)

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
    ''' Lang title (H2, used for archived files)
    '''
    if lang == '':
        return '## All language'
    return '## ' + lang.capitalize()

def convert_readme_lang_title(lang):
    '''README.md 中的语言子标题 (H3)'''
    if lang == '':
        return '### All language'
    return '### ' + lang.capitalize()

def find_header_end(lines):
    """找到 header 结束位置（第一个 ## 所在行的索引）"""
    for i, line in enumerate(lines):
        if line.startswith('## '):
            return i
    return len(lines)

def insert_date_section(lines, date_title):
    """在正确位置插入新的日期段落（保持日期降序）"""
    new_date = date_title[3:].strip()  # "2026-02-16"
    header_end = find_header_end(lines)

    # 从 header 之后开始，找到第一个日期 < new_date 的位置
    insert_pos = len(lines)
    for i in range(header_end, len(lines)):
        if lines[i].startswith('## ') and re.match(r'^## \d{4}-\d{2}-\d{2}$', lines[i].strip()):
            existing_date = lines[i][3:].strip()
            if existing_date < new_date:
                insert_pos = i
                break

    # 插入: date_title + 空行
    lines.insert(insert_pos, '')
    lines.insert(insert_pos, date_title)
    return lines

def has_lang_under_date(lines, date_title, lang_title):
    """检查在指定日期段落内是否存在指定语言子标题"""
    in_date_section = False
    for line in lines:
        if line.strip() == date_title:
            in_date_section = True
            continue
        if in_date_section:
            if line.startswith('## ') and not line.startswith('### '):
                return False  # 进入下一个日期段落
            if line.strip() == lang_title:
                return True
    return False

def insert_lang_under_date(lines, date_title, lang_title, lang):
    """在日期段落内按 LANG_ORDER 顺序插入语言子标题"""
    lang_display = lang if lang else 'All language'
    target_order = LANG_ORDER.index(lang_display) if lang_display in LANG_ORDER else len(LANG_ORDER)

    # 找到 date_title 所在行
    date_idx = None
    for i, line in enumerate(lines):
        if line.strip() == date_title:
            date_idx = i
            break

    if date_idx is None:
        return lines

    # 在日期段落内找到正确的插入位置
    insert_pos = None
    for i in range(date_idx + 1, len(lines)):
        if lines[i].startswith('## ') and not lines[i].startswith('### '):
            # 到达下一个日期段落，在此之前插入
            insert_pos = i
            break
        if lines[i].startswith('### '):
            existing_lang = lines[i][4:].strip()
            existing_order = LANG_ORDER.index(existing_lang) if existing_lang in LANG_ORDER else len(LANG_ORDER)
            if existing_order > target_order:
                insert_pos = i
                break

    if insert_pos is None:
        insert_pos = len(lines)

    # 插入: lang_title + 空行
    lines.insert(insert_pos, '')
    lines.insert(insert_pos, lang_title)
    return lines

def insert_entries_after_lang(lines, date_title, lang_title, entry_text):
    """在指定日期段落的指定语言标题后插入条目"""
    in_date = False
    for i, line in enumerate(lines):
        if line.strip() == date_title:
            in_date = True
            continue
        if in_date and line.startswith('## ') and not line.startswith('### '):
            break  # 超出日期段落
        if in_date and line.strip() == lang_title:
            # 找到空行后的插入位置
            insert_pos = i + 1
            if insert_pos < len(lines) and lines[insert_pos] == '':
                insert_pos += 1
            # 插入条目
            entry_lines = entry_text.rstrip('\n').split('\n')
            for j, entry_line in enumerate(entry_lines):
                lines.insert(insert_pos + j, entry_line)
            return lines
    return lines

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
    """从 README.md 内容中提取指定月份的所有条目（兼容新旧格式）

    返回: {'All language': ['* 【2025-11-30】...', ...], 'Python': [...], ...}
    """
    entries_by_lang = {}
    current_lang = None

    for line in content.split('\n'):
        # 新格式: ## YYYY-MM-DD 是日期标题，跳过
        if line.startswith('## ') and re.match(r'^## \d{4}-\d{2}-\d{2}$', line.strip()):
            continue

        # 新格式: ### Language 是语言标题
        if line.startswith('### '):
            current_lang = line[4:].strip()
            continue

        # 旧格式兼容: ## Language（非日期）
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

    content_lines = []
    processed_langs = set()

    for lang in LANG_ORDER:
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
    """清理 README.md 中超过指定天数的条目，并清理空段落"""
    cutoff_date = datetime.datetime.now().date() - datetime.timedelta(days=days_to_keep)

    # 第一遍：删除过期条目
    new_lines = []
    removed_count = 0
    kept_count = 0

    for line in content.split('\n'):
        if line.startswith('* 【'):
            entry_date = parse_entry_date(line)
            if entry_date and entry_date < cutoff_date:
                removed_count += 1
                continue
            kept_count += 1
        new_lines.append(line)

    logger.info(f"[Cleanup] Removed {removed_count} old entries (before {cutoff_date}), kept {kept_count}")

    # 第二遍：清理空的日期段落和语言子标题
    cleaned_lines = cleanup_empty_sections(new_lines)

    return '\n'.join(cleaned_lines)

def cleanup_empty_sections(lines):
    """清理空的日期段落和语言子标题"""
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 检测日期标题
        if re.match(r'^## \d{4}-\d{2}-\d{2}$', line.strip()):
            # 收集这个日期段落的所有行
            section_lines = [line]
            j = i + 1
            while j < len(lines):
                if lines[j].startswith('## ') and not lines[j].startswith('### '):
                    break  # 下一个日期段落或其他 H2
                section_lines.append(lines[j])
                j += 1

            # 检查此段落是否包含条目
            has_entries = any(l.startswith('* 【') for l in section_lines)
            if has_entries:
                cleaned_section = cleanup_empty_lang_subsections(section_lines)
                result.extend(cleaned_section)
            # 否则整个日期段落丢弃

            i = j
        else:
            result.append(line)
            i += 1

    return result

def cleanup_empty_lang_subsections(section_lines):
    """在一个日期段落内，清理没有条目的语言子标题"""
    result = []
    i = 0
    while i < len(section_lines):
        line = section_lines[i]
        if line.startswith('### '):
            # 收集这个语言子标题的行
            sub_lines = [line]
            j = i + 1
            while j < len(section_lines):
                if section_lines[j].startswith('### ') or (section_lines[j].startswith('## ') and not section_lines[j].startswith('### ')):
                    break
                sub_lines.append(section_lines[j])
                j += 1

            has_entries = any(l.startswith('* 【') for l in sub_lines)
            if has_entries:
                result.extend(sub_lines)
            i = j
        else:
            result.append(line)
            i += 1
    return result

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