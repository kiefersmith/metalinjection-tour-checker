import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import json
import os
import logging
import sys
import re
#Simport spacy

from db import init_db, insert_article

# Email configuration
EMAIL_ADDRESS = "kieferisgreat@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = "kieferisgreat@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Monitoring configuration
URL = "https://metalinjection.net/category/tour-dates"
CHECK_INTERVAL = 12*3600  # in seconds
CONTENT_FILE = "articles/previous_articles.json"
SEARCH_CITIES = ["Raleigh","Greensboro","Charlotte","Jacksonville","Chapel Hill","Hillsborough","Asheville"]

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
# nlp = spacy.load("en_core_web_sm")


def get_page_content(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def load_previous_articles():
    """Loads previously stored articles from a file."""
    try:
        with open(CONTENT_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []  # Return an empty list if no previous data exists

def save_articles(articles):
    """Saves current articles to a file for future comparison."""
    with open(CONTENT_FILE, "w") as file:
        json.dump(articles, file, indent=2)

def find_new_articles(new_articles, old_articles):
    """Finds new articles by comparing old and new lists."""
    old_urls = {article["url"] for article in old_articles}  # Convert old URLs to a set
    return [article for article in new_articles if article["url"] not in old_urls]

def extract_content(content):
    content_list = []
    c = BeautifulSoup(content, "html.parser").find("div", id="zox-home-cont-wrap")
    for cc in c.find_all("div", class_="zox-art-title"):
        href = cc.find("a")['href']
        h2 = cc.find("h2").get_text(strip=True)
        content_list.append({"title": h2, "url": href})
    return content_list

def find_city(content_list):
    article_list = []
    for content in content_list:
        found = False
        response = get_page_content(content["url"])
        c = BeautifulSoup(response, "html.parser").find("div", class_="zox-post-main")
        for cc in c.find_all("p"):
            for city in SEARCH_CITIES:
                if city in cc.text:
                    found = True
                    break

        if found:
            article_list.append(content)

    return article_list

def extract_all_caps_bands(text):
    pattern = r"\b[A-Z0-9][A-Z0-9\s&\-/]{1,}\b"
    matches = re.findall(pattern, text)
    bands = set()

    for m in matches:
        m_clean = m.strip()
        if len(m_clean) < 3:
            continue
        # Reject if it's only digits or mostly digits
        if re.fullmatch(r"[0-9\s\-\/]+", m_clean):
            continue
        # Reject Roman numerals (optional)
        if re.fullmatch(r"[IVXLCDM]+", m_clean) and len(m_clean) < 6:
            continue
        
        split_parts = [part.strip() for part in re.split(r"\s*&\s*", m_clean) if part.strip()]
        bands.update(split_parts)

    return list(bands)

def extract_band_names(title, article_text=None):
    # --- Step 1: Parse from title ---
    title_bands = extract_all_caps_bands(title)

    # --- Step 2: Optional NER from article body ---
    ner_bands = []
    if article_text:
        doc = nlp(article_text)
        ner_bands = [ent.text.strip() for ent in doc.ents if ent.label_ == "ORG"]

    # --- Step 3: Merge and deduplicate ---
    all_bands = list(set(title_bands + ner_bands))
    return all_bands

def format_articles(articles):
    email_body = "Here are the latest articles:\n"
    for article in articles:
        email_body += f'- {article["title"]} {article["url"]}\n'

    return email_body

def format_city_articles(articles):
    email_body = "These announcements have a city of interest in them:\n"
    for article in articles:
        email_body += f'- {article["title"]} {article["url"]}\n'

    return email_body

def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
    logging.info("sending email")

def monitor_page():
    try:
        init_db()
        content = get_page_content(URL)
        new_articles = extract_content(content)
        previous_articles = load_previous_articles()
        articles_to_send = find_new_articles(new_articles, previous_articles)
        articles_city = find_city(articles_to_send)

        if articles_to_send:
            logging.info("Found articles to send")
            save_articles(articles_to_send)

            # Save to DB
            for article in articles_to_send:
                city_match = article in articles_city
                bands = extract_band_names(article["title"]) # I think we can add article["body"] here but not sure
                insert_article(article["title"], bands, article["url"], city_match)

            email_body = format_city_articles(articles_city)
            email_body += "\n" + format_articles(articles_to_send)
            logging.debug(email_body)
            send_email(
                "Metalinjection Tour Page Update Detected",
                email_body
            )
        else:
            logging.info("No changes found.")

    except Exception as e:
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    while True:
        monitor_page()
        time.sleep(CHECK_INTERVAL)