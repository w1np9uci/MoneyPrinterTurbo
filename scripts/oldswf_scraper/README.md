# OldSWF Scraper CLI

A Python CLI tool to extract and download SWF files from oldswf.com game pages.

## Features

- Extract SWF files from oldswf.com game pages using static HTML parsing
- Optional Playwright fallback for dynamic content extraction
- Concurrent downloads with configurable concurrency
- Automatic retry with exponential backoff for transient errors
- CSV index file tracking all downloads
- Support for batch processing from file
- Progress bars for downloads

## Installation

### Basic Installation

```bash
pip install -r scripts/oldswf_scraper/requirements.txt
```

### With Playwright Support

If you want to use the `--use-playwright` option for dynamic content extraction:

```bash
pip install -r scripts/oldswf_scraper/requirements.txt
python -m playwright install chromium
```

Or use the Makefile target:

```bash
make scraper-setup
```

## Usage

### Basic Usage

Download a single game by URL:
```bash
python scripts/oldswf_scraper/main.py https://oldswf.com/game/18037
```

Download a single game by ID:
```bash
python scripts/oldswf_scraper/main.py 18037
```

Download multiple games:
```bash
python scripts/oldswf_scraper/main.py 18037 12345 67890
```

### Advanced Options

Use Playwright fallback (for pages where static parsing fails):
```bash
python scripts/oldswf_scraper/main.py --use-playwright 18037
```

Process games from a file:
```bash
python scripts/oldswf_scraper/main.py --from-file urls.txt
```

Custom output directory:
```bash
python scripts/oldswf_scraper/main.py --out-dir my_swf_files 18037
```

Adjust concurrency:
```bash
python scripts/oldswf_scraper/main.py --concurrency 8 18037 12345 67890
```

Add delay between requests:
```bash
python scripts/oldswf_scraper/main.py --delay-ms 1000 18037
```

Configure retries and timeout:
```bash
python scripts/oldswf_scraper/main.py --retries 5 --timeout 60 18037
```

### Combined Example

```bash
python scripts/oldswf_scraper/main.py \
  --from-file urls.txt \
  --out-dir swf_downloads \
  --use-playwright \
  --concurrency 8 \
  --delay-ms 500 \
  --retries 5 \
  --timeout 60
```

## Input File Format

When using `--from-file`, create a text file with one game URL or ID per line:

```
https://oldswf.com/game/18037
12345
67890
# Comments are supported (lines starting with #)
https://oldswf.com/game/99999
```

## Output

### Directory Structure

The tool creates the following structure:

```
swf_downloads/
├── downloads.csv
├── game1.swf
├── game2.swf
└── ...
```

### CSV Index File

The `downloads.csv` file tracks all download attempts with the following columns:

- `game_id`: The game ID extracted from the URL
- `title`: The page title (game name)
- `page_url`: The original game page URL
- `swf_url`: The resolved SWF file URL
- `local_path`: The local file path (if successfully downloaded)
- `status`: Download status (`success`, `SWF not found`, or `download failed`)

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `games` | Game page URLs or IDs (positional) | - |
| `--from-file` | Read game URLs/IDs from a file | - |
| `--out-dir` | Output directory for downloads | `./swf_downloads` |
| `--use-playwright` | Enable Playwright fallback for dynamic extraction | `false` |
| `--concurrency` | Number of concurrent downloads | `4` |
| `--delay-ms` | Delay in milliseconds between requests | `0` |
| `--retries` | Number of retry attempts for failed downloads | `3` |
| `--timeout` | Request timeout in seconds | `30` |

## How It Works

### Static Extraction

The tool first attempts to extract SWF URLs from the page HTML by looking for:
- `loadSwf('...')` JavaScript calls
- `file: '...'` properties
- `src='...'` attributes
- `data='...'` attributes
- Paths under `/data/swf/`

### Playwright Fallback

If static extraction fails and `--use-playwright` is enabled, the tool:
1. Opens the page in a headless Chromium browser
2. Captures all network requests
3. Filters for URLs ending with `.swf`
4. Uses the first matching URL

### Download

The tool downloads files with:
- Proper headers (User-Agent, Referer)
- Streaming to handle large files
- Progress bars for visual feedback
- Automatic retry with exponential backoff for transient errors (429, 5xx, timeouts)
- Original filename preservation (query strings stripped)

## Error Handling

The tool gracefully handles:
- Pages where SWF cannot be found (logged to CSV with "SWF not found" status)
- Network errors (retried with backoff)
- HTTP errors (429, 5xx retried; others fail immediately)
- Invalid URLs or IDs (skipped with error message)

## Examples

### Example 1: Quick Single Download

```bash
python scripts/oldswf_scraper/main.py 18037
```

Output:
```
Starting scraper with 1 game(s)...
Output directory: /path/to/swf_downloads
Concurrency: 4
Playwright fallback: disabled

Processing game 18037: https://oldswf.com/game/18037
Found SWF: https://oldswf.com/data/swf/game18037.swf
Title: Game Title - Play on OldSWF
Downloaded to: swf_downloads/game18037.swf

Done! Results saved to: swf_downloads/downloads.csv
```

### Example 2: Batch Processing with Playwright

```bash
python scripts/oldswf_scraper/main.py --use-playwright --from-file games.txt --concurrency 2
```

### Example 3: Conservative Scraping

```bash
python scripts/oldswf_scraper/main.py --concurrency 1 --delay-ms 2000 --retries 5 18037 12345
```

## Troubleshooting

### Playwright Not Found

If you see an error about Playwright not being installed:

```bash
pip install playwright
python -m playwright install chromium
```

### Rate Limiting

If you encounter rate limiting (HTTP 429), try:
- Reducing `--concurrency` to 1 or 2
- Adding `--delay-ms 1000` or higher
- Increasing `--retries` to allow more retry attempts

### Timeout Errors

If downloads timeout frequently:
- Increase `--timeout` to 60 or higher
- Check your network connection
- Try processing fewer games at once

## License

This tool is part of the MoneyPrinterTurbo project and follows the same MIT license.
