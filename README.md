# Google Scholar Self-Citation Checker

This script scrapes a Google Scholar author's profile page to identify their publications and the papers that cite them. It then analyzes these citations to determine the extent of self-citation, providing both an overall summary and a per-paper breakdown. 

The script can define self-citation in two ways:
1.  **Any common author (default):** A citation is considered a self-cite if any author of the original paper is also an author of the citing paper.
2.  **Last author as source:** A citation is considered a self-cite if the *last author* of the original paper is an author of the citing paper. This is activated with the `--last_author_is_self_source` flag.

## Features

*   Fetches all publications for a given Google Scholar author URL.
*   For each publication, retrieves papers that cite it.
*   Normalizes author names to handle variations in formatting for more accurate matching.
*   Calculates self-citations based on the chosen logic (any common author or last author).
*   Generates a CSV report (`<author_id>_citations_report.csv`) detailing original papers, citing papers, and self-citation status.
*   Prints a summary report to the console.
*   Includes basic CAPTCHA handling (manual intervention required).

## Prerequisites

1.  **Python 3.7+**
2.  **pip** (Python package installer)
3.  **Google Chrome** browser installed.
4.  **ChromeDriver**: The version of ChromeDriver must match your installed Google Chrome version. 
    *   Download from: [https://chromedriver.chromium.org/downloads](https://chromedriver.chromium.org/downloads)
    *   Ensure `chromedriver.exe` (or `chromedriver` on Linux/macOS) is in your system's PATH, or place it in the same directory as `main.py`.

## Installation

1.  **Clone the repository or download `main.py`**.

2.  **Install required Python packages**:
    Open a terminal or command prompt in the script's directory and run:
    ```bash
    pip install pandas requests beautifulsoup4 tqdm selenium matplotlib
    ```
    (Note: `matplotlib` is imported but not actively used in the current self-citation logic; it might be a remnant from previous script versions. `requests` is also imported but primary fetching is done via Selenium).

## Usage

Run the script from the command line:

```bash
python main.py --author_url "<GOOGLE_SCHOLAR_AUTHOR_URL>" [OPTIONS]
```

**Required Argument:**

*   `--author_url "<URL>"`: The full URL of the Google Scholar author's homepage.
    *   Example: `"https://scholar.google.com/citations?user=XXXXXXXXXXXX&hl=en"`

**Optional Arguments:**

*   `--csvpath <PATH>`: Path to save the exported CSV file (default: current folder).
*   `--notsavecsv`: If present, results will not be saved to a CSV file.
*   `--debug`: If present, enables verbose debug output during script execution.
*   `--last_author_is_self_source`: If present, defines self-citation based on the last author of the original paper being an author in the citing paper. Otherwise, any common author constitutes a self-cite.

**Example:**

```bash
python main.py --author_url "https://scholar.google.com/citations?user=your_author_id&hl=en" --debug --last_author_is_self_source
```

## Output

1.  **Console Output:**
    *   Progress of fetching publications and citations.
    *   A summary report including:
        *   Overall self-citation statistics (total self-cites, total citations, percentage).
        *   A per-paper breakdown showing self-citation counts and percentages for each of the author's publications.

2.  **CSV File (`<author_id>_citations_report.csv`):**
    *   Saved in the path specified by `--csvpath` (or the current directory by default), unless `--notsavecsv` is used.
    *   Columns include:
        *   `original_paper_title`
        *   `original_paper_authors` (original author string)
        *   `original_paper_year`
        *   `citing_paper_title`
        *   `citing_paper_authors` (original author string from citing paper)
        *   `is_self_citation` (True/False)
        *   `original_paper_normalized_authors` (list of normalized names for the original paper)
        *   `citing_paper_normalized_authors` (list of normalized names for the citing paper)

## CAPTCHA Handling

Google Scholar may present a reCAPTCHA if it detects unusual traffic (which can happen during scraping).
*   The script will pause and print a message in the console asking you to solve the CAPTCHA.
*   The Selenium-controlled Chrome browser window will display the CAPTCHA.
*   **Manually solve the CAPTCHA in the browser window.**
*   Once solved, return to the console and press `Enter` to allow the script to continue.

## Notes

*   The script relies on the structure of Google Scholar pages. Changes to the Google Scholar website may break the script.
*   Author name normalization is a complex task. The current implementation handles many common formats but might not be exhaustive for all variations of author name listings.
*   Be mindful of Google Scholar's terms of service when using this script.
