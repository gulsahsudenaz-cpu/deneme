.PHONY: help build run dev test clean deploy health

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build Docker image
	docker build -t support-chat .

run: ## Run with Docker Compose
	docker-compose up -d

dev: ## Run development environment
	docker-compose up --build

test: ## Run tests
	pytest tests/ -v --cov=app

clean: ## Clean Docker containers and images
	docker-compose down -v
	docker system prune -f

deploy: ## Deploy to production
	docker-compose -f docker-compose.prod.yml up -d --build

health: ## Check application health
	curl -f http://localhost:8000/health || echo "Health check failed"

logs: ## Show application logs
	docker-compose logs -f app

shell: ## Open shell in container
	docker-compose exec app bash