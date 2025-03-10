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
SEARCH_CITIES = ["Raleigh","Greensboro","Charlotte","Jacksonville","Chapel Hill", "Hillsborough"]
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

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

def format_articles(articles):
    email_body = "Here are the latest articles:\n"
    for article in articles:
        email_body += f'- {article["title"]} {article["url"]}\n'

    return email_body

def format_city_articles(articles):
    email_body = "These announcements have Raleigh in them:\n"
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
        content = get_page_content(URL)
        new_articles = extract_content(content)
        previous_articles = load_previous_articles()
        articles_to_send = find_new_articles(new_articles, previous_articles)
        articles_city = find_city(articles_to_send)

        if articles_to_send:
            logging.info("Found articles to send")
            # for article in articles_to_send:
            #     print(f"- {article['title']} ({article['url']})")
            save_articles(new_articles)
            email_body = format_city_articles(articles_city)
            email_body += "\n" + format_articles(new_articles)
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