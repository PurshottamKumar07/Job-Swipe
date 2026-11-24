import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque


class Crawler:

    def __init__(self, start_url, max_pages=50):
        self.queue = deque([start_url])
        self.visited = set()
        self.max_pages = max_pages

        parsed = urlparse(start_url)
        self.domain = parsed.netloc

    def crawl(self):

        while self.queue and len(self.visited) < self.max_pages:

            url = self.queue.popleft()

            if url in self.visited:
                continue

            print("Crawling:", url)

            self.visited.add(url)

            try:
                response = requests.get(
                    url,
                    headers={
                        "User-Agent": "MyCrawler/1.0"
                    },
                    timeout=10
                )

                if response.status_code != 200:
                    continue

            except requests.RequestException:
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            for a in soup.find_all("a", href=True):

                link = urljoin(url, a["href"])

                parsed = urlparse(link)

                # Only crawl the same domain
                if parsed.netloc != self.domain:
                    continue

                # Don't crawl the same page twice
                if link not in self.visited:
                    self.queue.append(link)


crawler = Crawler(
    "https://books.toscrape.com/",
    max_pages=20
)

crawler.crawl()