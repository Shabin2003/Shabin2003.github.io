"""Build the portfolio into _site/ from site.yml and public GitHub repos."""
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
OUT = ROOT / "_site"
API = "https://api.github.com"
FEATURED_TOPIC = "featured"
HIDE_TOPIC = "hide-from-portfolio"
# Some hosts refuse scripts but work in a browser, so these still count as live.
LIVE_ERROR_CODES = {401, 403, 429}

(ROOT / "logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(funcName)s() %(message)s",
    handlers=[logging.FileHandler(ROOT / "logs" / "build.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def check_response(response):
    if not response.ok:
        log.error("%s returned %s: %s", response.url, response.status_code, response.text[:500])
    response.raise_for_status()


def fetch_repos(user):
    repos, page = [], 1
    while True:
        response = requests.get(
            f"{API}/users/{user}/repos",
            params={"per_page": 100, "page": page, "sort": "pushed"},
            headers=github_headers(),
            timeout=30,
        )
        check_response(response)
        batch = response.json()
        repos += batch
        if len(batch) < 100:
            log.info("fetched %d public repos for %s", len(repos), user)
            return repos
        page += 1


def fetch_cover_images(user):
    """Return {repo name: custom social preview URL}. GitHub's GraphQL API requires a token."""
    if not os.environ.get("GITHUB_TOKEN"):
        log.info("GITHUB_TOKEN not set, skipping cover images")
        return {}
    query = """query($login: String!) {
      user(login: $login) {
        repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER) {
          nodes { name usesCustomOpenGraphImage openGraphImageUrl }
        }
      }
    }"""
    response = requests.post(
        f"{API}/graphql",
        json={"query": query, "variables": {"login": user}},
        headers=github_headers(),
        timeout=30,
    )
    check_response(response)
    body = response.json()
    if "errors" in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    nodes = body["data"]["user"]["repositories"]["nodes"]
    return {n["name"]: n["openGraphImageUrl"] for n in nodes if n["usesCustomOpenGraphImage"]}


def live_url(url):
    """Return url if it responds, otherwise None so the site never shows a broken demo."""
    if not url:
        return None
    try:
        response = requests.get(url, timeout=15, stream=True, headers={"User-Agent": "portfolio-build"})
        response.close()
    except requests.RequestException as error:
        log.warning("hiding demo %s: %s", url, error)
        return None
    if response.status_code < 400 or response.status_code in LIVE_ERROR_CODES:
        return url
    log.warning("hiding demo %s: HTTP %s", url, response.status_code)
    return None


def to_project(repo, images):
    return {
        "name": repo["name"],
        "description": (repo["description"] or "").strip(),
        "url": repo["html_url"],
        "demo": live_url(repo["homepage"]),
        "language": repo["language"],
        "topics": sorted(t for t in repo["topics"] if t != FEATURED_TOPIC),
        "stars": repo["stargazers_count"],
        "updated": repo["pushed_at"][:10],
        "featured": FEATURED_TOPIC in repo["topics"],
        "image": images.get(repo["name"]),
    }


def select_projects(repos, user, images):
    excluded = {user.lower(), f"{user.lower()}.github.io"}
    projects = [
        to_project(r, images)
        for r in repos
        if not r["fork"] and not r["archived"] and HIDE_TOPIC not in r["topics"] and r["name"].lower() not in excluded
    ]
    projects.sort(key=lambda p: p["updated"], reverse=True)
    log.info("selected %d of %d repos", len(projects), len(repos))
    return projects


def person_schema(site):
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": site["name"],
        "url": site["url"],
        "description": site["description"],
        "sameAs": [link["url"] for link in site["links"] if link["url"].startswith("http")],
    }


def render(site, projects):
    env = Environment(loader=FileSystemLoader(ROOT), autoescape=select_autoescape(["html"]))
    return env.get_template("template.html").render(
        site=site,
        featured=[p for p in projects if p["featured"]],
        projects=projects,
        topics=sorted({t for p in projects for t in p["topics"]}),
        schema=person_schema(site),
        built=datetime.now(timezone.utc).strftime("%d %b %Y"),
    )


def main():
    site = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8"))
    repos = fetch_repos(site["github_user"])
    projects = select_projects(repos, site["github_user"], fetch_cover_images(site["github_user"]))

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    (OUT / "index.html").write_text(render(site, projects), encoding="utf-8")
    (OUT / "projects.json").write_text(json.dumps(projects, indent=2), encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site['url']}sitemap.xml\n", encoding="utf-8")
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{site['url']}</loc></url></urlset>\n",
        encoding="utf-8",
    )
    log.info("wrote site to %s", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("build failed")
        raise
