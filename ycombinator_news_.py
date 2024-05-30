from bs4 import BeautifulSoup
import csv
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time
import requests
import re

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
KEY = 'key.json'
SPREADSHEET_ID = '1v6jPy3qsobEraNWQ5j9QxkpWjxM6v8Xv8iz5EC-kPMI'
SHEET_NAME = 'News'

creds = service_account.Credentials.from_service_account_file(
    KEY, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=SHEET_NAME).execute()
values = result.get('values', [])

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

if not values:
    headers = ['Company', 'Title', 'URL', 'Date Posted', 'Time Posted',
               'User', 'User Profile', 'Category']
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=SHEET_NAME,
        valueInputOption='RAW',
        insertDataOption='INSERT_ROWS',
        body={'values': [headers]}
    ).execute()

driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
driver.get('https://news.ycombinator.com/newest')


def check_last_time_posted(soup):
    time_elems = soup.find_all('span', class_='age')
    if not time_elems:
        return None
    last_time_posted = time_elems[-1].text.strip()
    return last_time_posted


last_time_posted = ''
while last_time_posted != "2 hours ago":
    try:
        more_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, 'morelink'))
        )
        more_button.click()
        time.sleep(2)
    except Exception as e:
        print(f"An error occurred while clicking the more button: {e}")
        break

    response_text = driver.page_source
    soup = BeautifulSoup(response_text, 'lxml')
    last_time_posted = check_last_time_posted(soup)
    print(f"Last time posted: {last_time_posted}")

driver.quit()

soup = BeautifulSoup(response_text, 'lxml')
news_list = soup.find_all('tr', class_="athing")

existing_entries = set()
if os.path.isfile('news-found_4.csv'):
    with open('news-found_4.csv', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if row:
                existing_entries.add(tuple(row))


def get_synonyms(word):
    response = requests.get(f"https://api.datamuse.com/words?rel_syn={word}")
    synonyms = [word]
    if response.status_code == 200:
        data = response.json()
        for item in data:
            synonyms.append(item['word'])
    return synonyms


def classify_title(title):        
    base_release_keyword = ['release']
    tech_giants_keywords = ['apple', 'google', 'nvidia', 'microsoft', 'meta', 'tesla', 'amazon', 'oracle', 'alphabet']
    base_ai_keywords = ['ai model', 'a.i model', 'chat gpt', 'gpt', 'llm', 'ollama', 'llama', 'machine learning']
    base_finance_keywords = ['price', 'funding', 'dollar', 'euro', '$', '€',
                             '£', 'yen', 'investment', 'finance', 'budget', 'revenue', 'cost', 'benchmark']      

    realise_keyword = []
    for word in base_release_keyword:
        realise_keyword.extend(get_synonyms(word))  
    finance_keywords = []
    for word in base_finance_keywords:
        finance_keywords.extend(get_synonyms(word))

    title_lower = title.lower()

    if title_lower[0].isdigit():
        return 'Nul'
    if '?' in title_lower:
        return 'Question'
    elif re.search(r'\b(19|20)\d{2}\b', title_lower):
        return 'Yearly news'     
    if any(word in title_lower for word in realise_keyword):
        return 'Release'
    if any(word in title_lower for word in tech_giants_keywords):
        return 'Tech Giants'
    if any(word in title_lower for word in base_ai_keywords):
        return 'AI'
    if any(word in title_lower for word in finance_keywords):
        return 'Finances'
    else:
        return 'Others'


try:
    with open('news-found_4.csv', 'a', newline='', encoding='utf-8') as f:
        file = csv.writer(f)
        if not existing_entries:
            file.writerow(['Company', 'Title', 'URL', 'Date Posted', 'Time Posted',
                           'User', 'User Profile', 'Category'])

        for news in news_list:
            company_elem = news.find('span', class_='sitestr')
            company = company_elem.text.strip() if company_elem else 'news.ycombinator.com'
            title_sel = news.find('span', class_='titleline')
            title = title_sel.text.strip() if title_sel else 'N/A'
            url = title_sel.find('a').get('href').strip(
            ) if title_sel and title_sel.find('a') else 'N/A'
            url = 'https://news.ycombinator.com/' + \
                url if url.startswith('user?id=') else url

            metadata = news.find_next_sibling()
            time_elem = metadata.find('span', class_='age')
            time_posted = time_elem.get('title') if time_elem else 'N/A'
            date_posted, time_posted = time_posted.split(
                'T') if time_posted != 'N/A' else ('N/A', 'N/A')
            time_ago = time_elem.find('a').text.strip() if time_elem else 'N/A'
            user_sel = metadata.find(
                'a', class_='hnuser') if metadata else None
            user = user_sel.text.strip() if user_sel else 'N/A'
            user_profile = 'https://news.ycombinator.com/' + \
                user_sel.get('href').strip() if user_sel else 'N/A'

            category = classify_title(title)

            if category == 'Nul':
                continue

            new_entry = (company, title, url, date_posted, time_posted,
                         user, user_profile, category)

            if new_entry not in existing_entries:
                file.writerow(new_entry)
                existing_entries.add(new_entry)

                sheet.values().append(
                    spreadsheetId=SPREADSHEET_ID,
                    range=SHEET_NAME,
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body={'values': [list(new_entry)]}
                ).execute()

except ValueError as e:
    print(f"Error writing to file: {e}")

print(time_ago)
print()