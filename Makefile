.PHONY: build up down logs restart clean start dev

# Build the Docker image
build:
	docker compose -f docker/docker-compose.yml build

# Start the service
up:
	docker compose -f docker/docker-compose.yml up -d

# Stop the service
down:
	docker compose -f docker/docker-compose.yml down

# Show logs
logs:
	docker compose -f docker/docker-compose.yml logs -f

# Restart the service
restart:
	docker compose -f docker/docker-compose.yml restart

# Clean up everything
clean:
	docker compose -f docker/docker-compose.yml down -v
	docker image prune -f

# Build and start
start: build up

# Development mode with live logs
dev:
	docker compose -f docker/docker-compose.yml up --build
