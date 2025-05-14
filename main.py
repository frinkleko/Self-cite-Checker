import argparse
import datetime
import os
import sys
import time
import warnings
from dataclasses import dataclass
from time import sleep
from typing import List, Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium import webdriver

now = datetime.datetime.now()
current_year = now.year
MAX_CSV_FNAME = 255

# Websession Parameters
GSCHOLAR_URL = "https://scholar.google.com/scholar?start={}&q={}&hl=en&as_sdt=0,5"
YEAR_RANGE = ""  # &as_ylo={start_year}&as_yhi={end_year}'
# GSCHOLAR_URL_YEAR = GSCHOLAR_URL+YEAR_RANGE
STARTYEAR_URL = "&as_ylo={}"
ENDYEAR_URL = "&as_yhi={}"
ROBOT_KW = ["unusual traffic from your computer network", "not a robot"]

# Global WebDriver instance
driver: Optional[webdriver.Chrome] = None


@dataclass
class GoogleScholarConfig:
    author_url: str = ""  # URL of the Google Scholar author page
    save_csv: bool = True
    csvpath: str = "."
    debug: bool = False
    last_author_is_self_source: bool = False
    # Removed: keyword, nresults, sortby, plot_results, start_year, end_year, current_year


# --- Author Parsing and Normalization ---
def _normalize_author_name(name_part: str) -> Optional[str]:
    """Normalizes a single author name part to 'lastname,firstnamemiddle' format."""
    name = name_part.lower().strip()
    name = name.rstrip('*.0123456789 ')  # Remove common trailing junk

    if not name or name == "...":
        return None

    # Split on the first comma only, to handle "Lastname, Firstname Middle"
    name_components = name.split(',', 1)

    final_last_name = ""
    final_first_middle = ""

    if len(name_components) == 2:  # Format "Last, First Middle"
        temp_last = name_components[0].strip()
        # Clean first/middle name part: remove periods, strip, normalize spaces
        temp_first_middle = name_components[1].replace('.', '').strip()
        temp_first_middle = " ".join(temp_first_middle.split())  # Normalize multiple spaces to single

        if temp_last:  # Standard "Last, First"
            final_last_name = temp_last
            final_first_middle = temp_first_middle
        else:  # Original was ", First Middle", so treat "First Middle" as a full name string
            name_tokens = temp_first_middle.split()
            if not name_tokens:
                return None
            if len(name_tokens) == 1:  # e.g. ", LastnameOnly"
                final_last_name = name_tokens[0]
                # final_first_middle remains ""
            else:  # e.g. ", First Middle Lastname"
                final_last_name = name_tokens[-1]
                final_first_middle = " ".join(name_tokens[:-1])

    elif len(name_components) == 1:  # Format "First Middle Last" or just "Last"
        name_tokens = name_components[0].split()  # name_components[0] is the whole string here
        if not name_tokens:
            return None

        if len(name_tokens) == 1:  # Only one name part, assume it's a last name
            final_last_name = name_tokens[0]
            # final_first_middle remains ""
        else:
            final_last_name = name_tokens[-1]
            # Combine first/middle parts, remove periods, strip, normalize spaces
            temp_first_middle_parts = [p.replace('.', '').strip() for p in name_tokens[:-1]]
            final_first_middle = " ".join(filter(None, temp_first_middle_parts))
            # Normalize spaces again in case of empty strings from filter or initial multiple spaces
            final_first_middle = " ".join(final_first_middle.split())

    if not final_last_name:  # If no last name could be determined
        return None

    # Return "lastname,firstmiddle" or "lastname," if no first/middle part
    return f"{final_last_name},{final_first_middle}" if final_first_middle else f"{final_last_name},"

def get_normalized_authors(author_string: str) -> List[str]:
    """Parses an author string and returns an ordered list of normalized author names."""
    if not author_string or author_string == "N/A":
        return []

    # Replace variations of "and" with "," for consistent splitting
    author_string_cleaned = author_string.replace(", and ", ", ")
    author_string_cleaned = author_string_cleaned.replace(" and ", ", ")

    author_parts = [part.strip() for part in author_string_cleaned.split(',')]

    normalized_authors = []
    for part in author_parts:
        if not part:  # Skip empty parts that might result from multiple commas
            continue
        normalized = _normalize_author_name(part)
        if normalized:
            normalized_authors.append(normalized)

    return normalized_authors # Return ordered list, removed list(set(...))

# --- End Author Parsing and Normalization ---

def setup_driver() -> webdriver.Chrome:
    global driver
    try:
        from selenium.webdriver.chrome.options import Options  # Already imported above
    except Exception as e:  # Should not happen if imports are correct
        print(f"Error importing Selenium options: {e}")
        print("Please ensure Selenium is installed correctly.")
        raise

    if config_obj.debug:  # Assuming config_obj is accessible or pass debug flag
        print("DEBUG: Setting up Chrome WebDriver...")

    chrome_options = Options()
    # chrome_options.add_argument("--headless") # Optional: run headless
    chrome_options.add_argument("disable-infobars")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument(
        "--disable-dev-shm-usage"
    )  # Important for Docker/CI environments
    # Suppress DevTools listening message
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

    try:
        driver = webdriver.Chrome(options=chrome_options)
        if config_obj.debug:
            print("DEBUG: WebDriver initialized.")
    except WebDriverException as e:
        print(f"WebDriverException occurred: {e}")
        print(
            "Please ensure that ChromeDriver is installed and in your PATH, or specified via a service object."
        )
        print("Download from: https://chromedriver.chromium.org/downloads")
        raise
    return driver


def get_content_with_selenium(url: str) -> Optional[bytes]:
    global driver
    if driver is None:
        if config_obj.debug:
            print(
                "DEBUG: WebDriver not initialized in get_content_with_selenium. Setting up now."
            )
        driver = setup_driver()

    if config_obj.debug:
        print(f"DEBUG: Selenium fetching URL: {url}")
    driver.get(url)

    # Check for CAPTCHA, simple version
    page_content_for_check = driver.page_source
    if any(kw.lower() in page_content_for_check.lower() for kw in ROBOT_KW):
        print("CAPTCHA or robot check detected. Please solve it in the browser.")
        print(f"URL: {url}")
        input("After solving the CAPTCHA, press Enter here to continue...")
        # Re-fetch content after manual intervention
        driver.get(url)  # Re-navigate in case the page changed
        if config_obj.debug:
            print("DEBUG: Re-fetching content after CAPTCHA.")

    # It's better to get innerHTML of body to match original logic if that's what's expected
    # However, driver.page_source gives the full HTML. For BeautifulSoup, page_source is fine.
    el = driver.find_element(By.XPATH, "/html/body")
    content = el.get_attribute("innerHTML")
    return content.encode("utf-8", errors="replace")


def fetch_author_publications(
    author_url: str, config: GoogleScholarConfig
) -> List[dict]:
    global driver
    if driver is None:
        if config.debug:
            print(
                "DEBUG: WebDriver not initialized in fetch_author_publications. Setting up now."
            )
        driver = setup_driver()

    if config.debug:
        print(f"DEBUG: Navigating to author page: {author_url}")
    driver.get(author_url)

    show_more_button_id = "gsc_bpf_more"
    max_show_more_clicks = 30  # Safety break
    clicks = 0
    while clicks < max_show_more_clicks:
        try:
            show_more_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, show_more_button_id))
            )
            if not show_more_button.is_enabled():
                if config.debug:
                    print(
                        "DEBUG: 'Show More' button is disabled. Assuming all publications are loaded."
                    )
                break

            driver.execute_script(
                "arguments[0].scrollIntoView(true);", show_more_button
            )
            sleep(0.3)  # Brief pause for scrolling
            driver.execute_script("arguments[0].click();", show_more_button)
            clicks += 1
            if config.debug:
                print(f"DEBUG: Clicked 'Show More' button ({clicks} clicks).")
            sleep(
                1.5
            )  # Wait for new results to load (can be made more robust with explicit waits for new content)
        except (TimeoutException, NoSuchElementException):
            if config.debug:
                print(
                    "DEBUG: 'Show More' button no longer found or clickable. Assuming all publications loaded."
                )
            break
        except Exception as e:
            if config.debug:
                print(f"DEBUG: Error clicking 'Show More': {e}")
            break

    if config.debug:
        print(
            "DEBUG: Finished clicking 'Show More'. Parsing publications from page source."
        )

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, "html.parser")

    publications = []
    pub_table = soup.find("table", id="gsc_a_t")
    if not pub_table:
        if config.debug:
            print("DEBUG: Publication table 'gsc_a_t' not found.")
        return publications

    for row in pub_table.find("tbody").find_all("tr", class_="gsc_a_tr"):
        title_tag = row.find("td", class_="gsc_a_t").find("a", class_="gsc_a_at")
        title = title_tag.text.strip() if title_tag else "N/A"

        authors_divs = row.find("td", class_="gsc_a_t").find_all(
            "div", class_="gs_gray"
        )
        authors_text = authors_divs[0].text.strip() if len(authors_divs) > 0 else "N/A"
        normalized_authors = get_normalized_authors(authors_text)
        
        cited_by_cell = row.find("td", class_="gsc_a_c")
        cited_by_link_tag = cited_by_cell.find("a") if cited_by_cell else None

        num_citations = 0
        cited_by_link = None
        if (
            cited_by_link_tag
            and cited_by_link_tag.text.strip().replace("Cited by ", "").isdigit()
        ):
            num_citations = int(cited_by_link_tag.text.strip().replace("Cited by ", ""))
            cited_by_url_part = cited_by_link_tag.get("href")
            if cited_by_url_part:
                if cited_by_url_part.startswith("http"):
                    cited_by_link = cited_by_url_part
                elif cited_by_url_part.startswith("/"):
                    cited_by_link = "https://scholar.google.com" + cited_by_url_part
                else:  # Fallback for unexpected formats
                    cited_by_link = "https://scholar.google.com/" + cited_by_url_part.lstrip('/')
        elif (
            cited_by_link_tag and cited_by_link_tag.text.strip() == ""
        ):  # Sometimes empty, means 0
            num_citations = 0
        elif cited_by_link_tag:  # Fallback if text is not just digits or "Cited by X"
            if config.debug:
                print(
                    f"DEBUG: Non-standard citation text: '{cited_by_link_tag.text}'. Assuming 0 or attempting parse."
                )
            # Attempt a more general parse if possible, otherwise default to 0
            try:  # Check if it's just a number (sometimes links without "Cited by")
                num_citations = int(cited_by_link_tag.text.strip())
                cited_by_url_part = cited_by_link_tag.get("href")
                if cited_by_url_part:
                    if cited_by_url_part.startswith("http"):
                        cited_by_link = cited_by_url_part
                    elif cited_by_url_part.startswith("/"):
                        cited_by_link = "https://scholar.google.com" + cited_by_url_part
                    else:  # Fallback for unexpected formats
                        cited_by_link = "https://scholar.google.com/" + cited_by_url_part.lstrip('/')
            except ValueError:
                num_citations = 0

        year_cell = row.find("td", class_="gsc_a_y")
        year_span = year_cell.find("span", class_="gsc_a_h") if year_cell else None
        year_text = year_span.text.strip() if year_span else ""
        year = (
            int(year_text) if year_text.isdigit() else 0
        )  # Default to 0 if not a number or missing

        pub_data = {
            "title": title,
            "authors": authors_text, # Keep original author string
            "normalized_authors": normalized_authors, # Add normalized list
            "year": year,
            "num_citations": num_citations,
            "cited_by_link": cited_by_link,
        }
        publications.append(pub_data)
        if config.debug:
            print(
                f"DEBUG: Parsed Pub - Title: {title}, Authors: {authors_text}, NormAuthors: {normalized_authors}, Year: {year}, Citations: {num_citations}, CiteLink: {cited_by_link}"
            )

    if config.debug:
        print(
            f"DEBUG: Finished fetching author publications. Found {len(publications)} publications."
        )
    else:
        print(f"Found {len(publications)} publications for the author.")
    return publications


def fetch_citations_for_paper(
    publication_title: str, cited_by_link_base: str, config: GoogleScholarConfig
) -> List[dict]:
    citing_papers = []
    if not cited_by_link_base:
        if config.debug:
            print(f"DEBUG: No 'cited_by_link' for '{publication_title}'. Skipping.")
        return citing_papers

    start_index = 0
    max_pages_to_fetch = 50  # Safety break for highly cited papers (50 pages * 10 results = 500 citations)

    if config.debug:
        print(
            f"DEBUG: Starting to fetch citations for: '{publication_title}' from base link: {cited_by_link_base}"
        )

    for page_num in range(max_pages_to_fetch):
        # Ensure base link doesn't already have a 'start' param we'd conflict with
        # Basic way: remove existing 'start=' if present, then add new one.
        # For simplicity, assume it's a clean base URL for citations.
        paginated_url = f"{cited_by_link_base}&start={start_index}"

        if config.debug:
            print(
                f"DEBUG: Fetching citations page {page_num + 1} (start={start_index}) for '{publication_title}' from URL: {paginated_url}"
            )

        try:
            page_content_bytes = get_content_with_selenium(
                paginated_url
            )  # Handles CAPTCHA
            if not page_content_bytes:
                if config.debug:
                    print(
                        f"DEBUG: No content from get_content_with_selenium for {paginated_url}. Stopping."
                    )
                break
            soup = BeautifulSoup(
                page_content_bytes.decode("utf-8", errors="replace"), "html.parser"
            )
        except Exception as e:
            if config.debug:
                print(
                    f"DEBUG: Error fetching or parsing citation page {paginated_url}: {e}"
                )
            break

        found_on_page = 0
        # Google Scholar search results structure (which "Cited by" pages are)
        paper_divs = soup.findAll("div", {"class": "gs_r gs_or gs_scl"})
        if not paper_divs and config.debug:
            print(
                f"DEBUG: No citation items found with class 'gs_r gs_or gs_scl' on page {paginated_url}."
            )

        for div in paper_divs:
            found_on_page += 1
            try:
                title_tag = div.find("h3", class_="gs_rt")
                citing_title = "N/A"
                if title_tag:
                    link_tag = title_tag.find("a")
                    if link_tag:
                        citing_title = link_tag.text.strip()
                    else:  # Title might not be a link (e.g. [CITATION] items)
                        citing_title = title_tag.text.strip()

                authors_div = div.find("div", class_="gs_a")
                citing_authors_full_text = (
                    authors_div.text.strip() if authors_div else "N/A"
                )

                # Heuristic to extract just authors from "Author1, Author2 - Journal, Year - Publisher"
                citing_authors_text = citing_authors_full_text.split(" - ")[0]
                normalized_citing_authors = get_normalized_authors(citing_authors_text)

                citing_papers.append({
                    "title": citing_title, 
                    "authors": citing_authors_text, # Keep original author string
                    "normalized_authors": normalized_citing_authors # Add normalized list
                })
                if config.debug:
                    print(
                        f"DEBUG: Found Citing Paper - Title: {citing_title}, Authors: {citing_authors_text}, NormAuthors: {normalized_citing_authors}"
                    )
            except Exception as e:
                if config.debug:
                    print(f"DEBUG: Error parsing a citing paper item: {e}")
                continue

        if found_on_page == 0:
            if config.debug:
                print(
                    f"DEBUG: No citing papers found on page {page_num + 1}. Assuming end of citations for '{publication_title}'."
                )
            break

        # Heuristic: if fewer than 10 results (standard page size), assume it's the last page.
        if found_on_page < 10:
            if config.debug:
                print(
                    f"DEBUG: Found {found_on_page} results on page {page_num + 1} (<10). Assuming end of citations."
                )
            break

        start_index += 10
        sleep(
            config.debug and 0.5 or 1.0
        )  # Politeness delay, slightly shorter if debugging fast.

    if config.debug:
        print(
            f"DEBUG: Finished fetching citations. Found {len(citing_papers)} citations for '{publication_title}'."
        )
    else:
        print(f"Found {len(citing_papers)} citations for '{publication_title}'.")
    return citing_papers


def google_scholar_spider(config: GoogleScholarConfig):
    if config.debug:
        print(f"DEBUG: Starting scrape for author URL: {config.author_url}")

    # 1. Fetch all publications by the author
    # Session object is not used by Selenium-based functions
    author_publications = fetch_author_publications(config.author_url, config)

    all_citations_data = []
    if not author_publications:
        print("No publications found for the author. Exiting.")
        return

    # 2. For each publication, fetch its citations
    for pub in tqdm(author_publications, desc="Processing author's publications"):
        if config.debug:
            print(
                f"DEBUG: Processing publication: '{pub['title']}' with {pub['num_citations']} citations."
            )

        if pub.get("cited_by_link") and pub.get("num_citations", 0) > 0:
            citations = fetch_citations_for_paper(
                pub["title"], pub["cited_by_link"], config
            )
            for citing_paper in citations:
                all_citations_data.append(
                    {
                        "original_paper_title": pub["title"],
                        "original_paper_authors": pub["authors"], # Original full string
                        "original_paper_normalized_authors": pub.get("normalized_authors", []),
                        "original_paper_year": pub.get("year"),
                        "citing_paper_title": citing_paper["title"],
                        "citing_paper_authors": citing_paper["authors"], # Original full string
                        "citing_paper_normalized_authors": citing_paper.get("normalized_authors", []),
                    }
                )
            sleep(
                0.5
            )  # Politeness delay between processing each paper's full citation list
        elif config.debug:
            print(
                f"DEBUG: Skipping citations for '{pub['title']}' (no citation link or zero citations)."
            )

    if all_citations_data:
        citations_df = pd.DataFrame(all_citations_data)
        print(
            f"Collected a total of {len(citations_df)} citing paper entries across all publications."
        )

        # --- Calculate Self-Citations ---
        def check_self_citation(row):
            orig_authors_list = row.get('original_paper_normalized_authors', [])
            citing_authors_list = row.get('citing_paper_normalized_authors', [])
            
            if not orig_authors_list or not citing_authors_list:
                return False

            if config_obj.last_author_is_self_source: # Use the global config_obj here
                # New logic: only the last author of the original paper matters
                last_author_original = orig_authors_list[-1]
                return last_author_original in set(citing_authors_list)
            else:
                # Original logic: any common author
                return bool(set(orig_authors_list).intersection(set(citing_authors_list)))

        citations_df['is_self_citation'] = citations_df.apply(check_self_citation, axis=1)
        # --- End Calculate Self-Citations ---

        if config.save_csv:
            author_id_part = (
                config.author_url.split("user=")[-1].split("&")[0]
                if "user=" in config.author_url
                else "unknown_author"
            )
            # Sanitize author_id_part for filename
            safe_author_id = "".join(
                c if c.isalnum() or c in ("_", "-") else "_" for c in author_id_part
            )
            output_filename = f"{safe_author_id}_citations_report"  # Changed filename for clarity

            # Columns to save - ensure normalized authors are also saved for transparency
            columns_to_save = [
                'original_paper_title', 'original_paper_authors', 'original_paper_year',
                'citing_paper_title', 'citing_paper_authors',
                'is_self_citation', 
                'original_paper_normalized_authors', 'citing_paper_normalized_authors' 
            ]
            save_data_to_csv(citations_df[columns_to_save], config.csvpath, output_filename)
        
        # --- Self-Citation Reporting --- 
        total_citations_found = len(citations_df)
        total_self_citations = citations_df['is_self_citation'].sum()

        print("\n--- Self-Citation Report ---")
        if total_citations_found > 0:
            overall_self_citation_percentage = (total_self_citations / total_citations_found) * 100
            print(f"Overall: {total_self_citations} self-citations out of {total_citations_found} total citations ({overall_self_citation_percentage:.1f}%).")
        else:
            print("No citations found to analyze.")

        # Per-paper summary
        print("\nDetails by Original Publication:")
        # Group by original paper title and its normalized authors to handle distinct papers with same title if any
        # For simplicity, just title, assuming titles are unique enough for this author
        for original_paper_title, group in citations_df.groupby('original_paper_title'):
            paper_total_citations = len(group)
            paper_self_citations = group['is_self_citation'].sum()
            authors_str = group['original_paper_authors'].iloc[0] # Get authors of this original paper
            year_str = group['original_paper_year'].iloc[0]

            if paper_total_citations > 0:
                paper_self_citation_percentage = (paper_self_citations / paper_total_citations) * 100
                print(f"  - '{original_paper_title}' ({authors_str}, {year_str}):")
                print(f"    {paper_self_citations} self-citations out of {paper_total_citations} total citations ({paper_self_citation_percentage:.1f}%)." )
            else: # Should not happen if group exists
                print(f"  - '{original_paper_title}' ({authors_str}, {year_str}): No citations found in the collected data.")
        print("---------------------------")

    else:
        print("No citation data collected for any publication.")

    # Old data processing parts are correctly commented out or removed.


def get_command_line_args() -> GoogleScholarConfig:
    parser = argparse.ArgumentParser(
        description="Google Scholar Author Citation Scraper"
    )
    parser.add_argument(
        "--author_url",
        type=str,
        required=True,
        help="URL of the Google Scholar author's homepage. E.g., 'https://scholar.google.com/citations?user=XXXXXXXXXXXX&hl=en'",
    )
    parser.add_argument(
        "--csvpath",
        type=str,
        default=".",
        help="Path to save the exported CSV file (default: current folder)",
    )
    parser.add_argument(
        "--notsavecsv",
        action="store_true",
        help="Do not save results to a CSV file (results will still be printed if any)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode for verbose output."
    )
    parser.add_argument(
        "--last_author_is_self_source", 
        action="store_true", 
        help="Consider only the last author of an original paper as the source for self-citation."
    )
    args = parser.parse_args()  # Changed from parse_known_args

    return GoogleScholarConfig(
        author_url=args.author_url,
        save_csv=not args.notsavecsv,
        csvpath=args.csvpath,
        debug=args.debug,
        last_author_is_self_source=args.last_author_is_self_source
    )


def save_data_to_csv(data: pd.DataFrame, path: str, base_filename: str) -> None:
    if not os.path.exists(path):
        try:
            os.makedirs(path)
            if config_obj.debug:  # Global config_obj for debug print
                print(f"DEBUG: Created directory: {path}")
        except OSError as e:
            print(f"Error creating directory {path}: {e}. Saving to current directory.")
            path = "."  # Fallback to current directory

    fpath_csv = os.path.join(path, base_filename.replace(" ", "_") + ".csv")
    # Ensure filename length is valid (MAX_CSV_FNAME is from old code, usually OS limits are around 255-260 total path)
    # A simpler approach might be to just ensure component is not excessively long.
    # For now, respecting MAX_CSV_FNAME for the filename part.

    # Get just the filename part to check its length
    file_part = os.path.basename(fpath_csv)
    if len(file_part) > MAX_CSV_FNAME:
        name, ext = os.path.splitext(file_part)
        name = name[: MAX_CSV_FNAME - len(ext) - 1]  # -1 for safety
        file_part = name + ext
        fpath_csv = os.path.join(path, file_part)
        if config_obj.debug:
            print(f"DEBUG: CSV filename truncated to: {fpath_csv}")

    try:
        data.to_csv(
            fpath_csv, encoding="utf-8", index=False
        )  # Usually don't need DataFrame index in CSV
        print(f"Results saved to: {fpath_csv}")
    except Exception as e:
        print(f"Error saving CSV to {fpath_csv}: {e}")


# Store config globally for access in setup_driver and save_data_to_csv debug prints
config_obj: Optional[GoogleScholarConfig] = None

if __name__ == "__main__":
    start_time = time.time()
    # driver is already declared global and Optional

    try:
        print("Getting command line arguments...")
        config_obj = get_command_line_args()  # Assign to global config_obj

        if config_obj.debug:
            print("DEBUG: Debug mode enabled.")
            print(f"DEBUG: Configuration: {config_obj}")

        # WebDriver will be set up by the first function that needs it (fetch_author_publications)
        # or explicitly here if preferred:
        # if driver is None:
        # driver = setup_driver() # setup_driver uses global config_obj for debug prints

        print("Running Google Scholar spider...")
        google_scholar_spider(config=config_obj)

    except Exception as e_main:
        print(f"An unexpected error occurred in the main script: {e_main}")
        import traceback

        traceback.print_exc()
    finally:
        if driver is not None:
            if config_obj and config_obj.debug:
                print("DEBUG: Quitting WebDriver.")
            driver.quit()
            print("WebDriver closed.")
        else:
            if config_obj and config_obj.debug:
                print("DEBUG: WebDriver was not initialized or already closed.")

        end_time = time.time()
        print(f"Total script execution time: {end_time - start_time:.2f} seconds")
