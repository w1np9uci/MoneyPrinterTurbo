.PHONY: scraper-setup scraper-help

scraper-setup:
	@echo "Setting up OldSWF scraper..."
	pip install -r scripts/oldswf_scraper/requirements.txt
	@echo "Installing Playwright browsers..."
	python -m playwright install chromium
	@echo "Setup complete! You can now use the scraper with --use-playwright option."

scraper-help:
	@echo "OldSWF Scraper Commands:"
	@echo "  make scraper-setup  - Install dependencies and Playwright browsers"
	@echo ""
	@echo "Usage examples:"
	@echo "  python scripts/oldswf_scraper/main.py 18037"
	@echo "  python scripts/oldswf_scraper/main.py --use-playwright 18037"
	@echo "  python scripts/oldswf_scraper/main.py --from-file urls.txt --concurrency 8"
