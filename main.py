from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from scholarly import scholarly
import time
import re
from collections import defaultdict
from tqdm import tqdm


def setup_driver():
    """Setup and return a Chrome webdriver with options"""
    service = Service()
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # set proxy if needed
    # options.add_argument('--proxy-server=https://127.0.0.1:7899')
    # https proxy
    
    # to download
    return webdriver.Chrome(
        service=service,
        options=options,
    )


def get_author_names(author_string):
    """Extract author names from the author string"""
    authors = re.split(r",|\band\b", author_string)
    return [name.strip().lower() for name in authors]


def is_self_citation(paper_authors, citing_paper_authors):
    """Check if there are any common authors between two papers"""
    paper_authors_set = set(paper_authors)
    citing_authors_set = set(citing_paper_authors)
    return bool(paper_authors_set & citing_authors_set)


def get_citations_from_page(driver, citation_url):
    """Get citations from a single page"""
    citations = []
    try:
        # Wait for citation elements to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "gs_ri"))
        )

        # Get all citation elements
        citation_elements = driver.find_elements(By.CLASS_NAME, "gs_ri")

        for element in citation_elements:
            try:
                title = element.find_element(By.CLASS_NAME, "gs_rt").text
                authors = element.find_element(By.CLASS_NAME, "gs_a").text
                citations.append({"title": title, "authors": authors})
            except:
                continue

    except TimeoutException:
        print("Timeout waiting for citations to load")

    return citations


def analyze_citations(scholar_profile_url):
    try:
        # Extract the author ID from the URL
        author_id = re.search(r"user=([^&]+)", scholar_profile_url).group(1)

        # Search for the author using the ID
        search_query = scholarly.search_author_id(author_id)
        author = scholarly.fill(search_query)

        # Setup webdriver
        driver = setup_driver()

        # Dictionary to store results
        results = defaultdict(dict)

        print(f"Analyzing citations for: {author['name']}")
        print("This might take a while...")

        # Get detailed information about each publication
        for pub in author["publications"]:
            pub_complete = scholarly.fill(pub)

            paper_title = pub_complete["bib"]["title"]
            paper_authors = get_author_names(pub_complete["bib"]["author"])
            total_citations = (
                pub_complete["num_citations"] if "num_citations" in pub_complete else 0
            )

            results[paper_title] = {
                "total_citations": total_citations,
                "non_self_citations": 0,
                "self_citations": 0,
            }
            # If there are citations, analyze them
            if total_citations > 0:
                # Construct citation URL
                citation_url = "https://scholar.google.com/scholar?cites={0}".format(
                    pub_complete["cites_id"][0]
                )

                # Get citations
                driver.get(citation_url)
                time.sleep(2)  # Wait for page to load

                citations = get_citations_from_page(driver, citation_url)

                # Analyze citations
                for citation in tqdm(citations):
                    citing_authors = get_author_names(citation["authors"])

                    if is_self_citation(paper_authors, citing_authors):
                        results[paper_title]["self_citations"] += 1
                    else:
                        results[paper_title]["non_self_citations"] += 1

            break

        # Close the driver
        driver.quit()

        # Print results
        print("\nResults:")
        print("-" * 80)
        for paper, stats in results.items():
            print(f"\nPaper: {paper}")
            print(f"Total citations: {stats['total_citations']}")
            print(f"Non-self citations: {stats['non_self_citations']}")
            print(f"Self citations: {stats['self_citations']}")
            print("-" * 80)

    except Exception as e:
        print(f"An error occurred: {e}")
        if "driver" in locals():
            driver.quit()


if __name__ == "__main__":
    scholar_url = input("Enter Google Scholar profile URL: ")
    analyze_citations(scholar_url)
