from datetime import datetime
import re
import zoneinfo

from bs4 import BeautifulSoup
import chevron
import duckdb
import requests


def create_tables(cursor):
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS movie (
        id UUID PRIMARY KEY,
        title_en TEXT NOT NULL)
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS showtime (
        movie UUID NOT NULL,
        showtime TIMESTAMP NOT NULL,
        is_full BOOLEAN NOT NULL,
        FOREIGN KEY(movie) REFERENCES movie(id))
    """
    )


def save_showtimes(cursor):
    html = requests.get("https://goldenscene.com").text
    r = re.compile(
        r"/movie/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    )
    movie_ids = set(r.findall(html))

    for movie_id in movie_ids:
        url = f"https://goldenscene.com/movie/{movie_id}"
        soup = BeautifulSoup(requests.get(url).text, "html.parser")
        title = soup.find("div", {"class": "is-size-4"}).text.strip()
        cursor.execute(
            "INSERT INTO movie (id, title_en) VALUES (?, ?)", (movie_id, title)
        )
        for section in soup.find_all("section", {"class": "showtime"}):
            date = section.find("div", {"class": "is-size-2"}).text.strip()
            date = date.split(".")
            month, day = date[0], date[1]

            for show in section.find_all("div", {"class": "showCell"}):
                time = show.find("div", {"class": "is-size-3"}).text.strip().split(":")
                time = datetime(
                    year=2024,
                    month=int(month),
                    day=int(day),
                    hour=int(time[0]),
                    minute=int(time[1]),
                )
                is_full = len(show.find_all("div", {"class": "full"})) > 0
                cursor.execute(
                    "INSERT INTO showtime (movie, showtime, is_full) VALUES (?, ?, ?)",
                    (movie_id, time, is_full),
                )


def generate_html(cursor, mustache_file, output_file):
    cursor.execute(
        """
  SELECT s.showtime, s.is_full, m.title_en, m.id
    FROM showtime s LEFT JOIN movie m ON (s.movie = m.id)
ORDER BY showtime ASC
"""
    )

    context = []
    date = None
    for showtime, is_full, title_en, movie_id in cursor.fetchall():
        today = datetime.now(zoneinfo.ZoneInfo("Asia/Hong_Kong")).date()
        if showtime.date() < today:
            # Ignore old showtimes
            continue

        if date is None or date != showtime.date():
            date = showtime.date()
            headline = "Today" if date == today else showtime.strftime("%A %m.%d")
            context.append({"headline": headline, "showtime": []})

        context[-1]["showtime"].append(
            {
                "is_full": is_full,
                "time": showtime.strftime("%H:%M"),
                "movie_id": movie_id,
                "title_en": title_en,
            }
        )

    output_file.write(chevron.render(mustache_file, {"date": context}))


if __name__ == "__main__":
    with duckdb.connect(":memory:") as conn:
        cursor = conn.cursor()
        create_tables(cursor)
        save_showtimes(cursor)
        with open("index.mustache") as mustache_file:
            with open("index.html", "w", encoding="utf-8") as output_file:
                generate_html(cursor, mustache_file, output_file)
