.PHONY: format lint typecheck test build verify up down migrate

format:
	npm run format
lint:
	npm run lint
typecheck:
	npm run typecheck
test:
	npm test
build:
	npm run build
verify:
	npm run verify
up:
	docker compose up --build
down:
	docker compose down
migrate:
	docker compose run --rm migrate
