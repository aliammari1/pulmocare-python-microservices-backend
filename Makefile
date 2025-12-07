# MedApp Microservices Automation Makefile
# This Makefile provides convenient commands for managing microservices

# Default variables
SERVICE_NAME ?= 
DOCKER_REGISTRY ?= your-registry
DOCKER_TAG ?= latest
ANSIBLE_DIR = ansible

# Colors for output
GREEN = \033[0;32m
YELLOW = \033[1;33m
RED = \033[0;31m
NC = \033[0m # No Color

.PHONY: help setup create-service build-service deploy-service list-services remove-service clean check-deps

# Default target
help: ## Display this help message
	@echo "$(GREEN)MedApp Microservices Automation$(NC)"
	@echo "=================================="
	@echo ""
	@echo "$(YELLOW)Available commands:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(YELLOW)Examples:$(NC)"
	@echo "  make create-service SERVICE_NAME=notifications"
	@echo "  make build-service SERVICE_NAME=notifications"
	@echo "  make deploy-service SERVICE_NAME=notifications"
	@echo "  make remove-service SERVICE_NAME=notifications"

check-deps: ## Check if required dependencies are installed
	@echo "$(YELLOW)Checking dependencies...$(NC)"
	@command -v ansible-playbook >/dev/null 2>&1 || { echo "$(RED)ansible-playbook is required but not installed.$(NC)" >&2; exit 1; }
	@command -v docker >/dev/null 2>&1 || { echo "$(RED)docker is required but not installed.$(NC)" >&2; exit 1; }
	@command -v kubectl >/dev/null 2>&1 || { echo "$(RED)kubectl is required but not installed.$(NC)" >&2; exit 1; }
	@echo "$(GREEN)✅ All dependencies are installed$(NC)"

setup: check-deps ## Setup the entire MedApp infrastructure
	@echo "$(YELLOW)Setting up MedApp infrastructure...$(NC)"
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/setup-infrastructure.yml
	@echo "$(GREEN)✅ Infrastructure setup complete$(NC)"

create-service: check-deps ## Create a new microservice (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make create-service SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Creating service: $(SERVICE_NAME)$(NC)"
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/create-microservice.yml -e service_name=$(SERVICE_NAME)
	@echo "$(GREEN)✅ Service $(SERVICE_NAME) created successfully$(NC)"

build-service: check-deps ## Build Docker image for a service (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make build-service SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Building service: $(SERVICE_NAME)$(NC)"
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/build-and-deploy.yml \
		-e service_name=$(SERVICE_NAME) \
		-e build_image=true \
		-e push_image=false \
		-e deploy_k8s=false \
		-e register_consul=false
	@echo "$(GREEN)✅ Service $(SERVICE_NAME) built successfully$(NC)"

push-service: check-deps ## Push Docker image for a service (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make push-service SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Pushing service: $(SERVICE_NAME)$(NC)"
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/build-and-deploy.yml \
		-e service_name=$(SERVICE_NAME) \
		-e build_image=false \
		-e push_image=true \
		-e deploy_k8s=false \
		-e register_consul=false
	@echo "$(GREEN)✅ Service $(SERVICE_NAME) pushed successfully$(NC)"

deploy-service: check-deps ## Deploy a service to Kubernetes (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make deploy-service SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Deploying service: $(SERVICE_NAME)$(NC)"
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/build-and-deploy.yml \
		-e service_name=$(SERVICE_NAME) \
		-e build_image=false \
		-e push_image=false \
		-e deploy_k8s=true \
		-e register_consul=true
	@echo "$(GREEN)✅ Service $(SERVICE_NAME) deployed successfully$(NC)"

full-deploy: check-deps ## Build, push, and deploy a service (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make full-deploy SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Full deployment for service: $(SERVICE_NAME)$(NC)"
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/build-and-deploy.yml \
		-e service_name=$(SERVICE_NAME) \
		-e build_image=true \
		-e push_image=true \
		-e deploy_k8s=true \
		-e register_consul=true
	@echo "$(GREEN)✅ Service $(SERVICE_NAME) fully deployed$(NC)"

list-services: check-deps ## List all services and their status
	@echo "$(YELLOW)Listing all services...$(NC)"
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/list-services.yml

remove-service: check-deps ## Remove a service (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make remove-service SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Removing service: $(SERVICE_NAME)$(NC)"
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/remove-service.yml \
		-e service_name=$(SERVICE_NAME) \
		-e remove_k8s=true \
		-e remove_consul=true \
		-e remove_docker=true \
		-e remove_files=false
	@echo "$(GREEN)✅ Service $(SERVICE_NAME) removed$(NC)"

clean-service: check-deps ## Completely remove a service including files (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make clean-service SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Completely cleaning service: $(SERVICE_NAME)$(NC)"
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/remove-service.yml \
		-e service_name=$(SERVICE_NAME) \
		-e remove_k8s=true \
		-e remove_consul=true \
		-e remove_docker=true \
		-e remove_files=true
	@echo "$(GREEN)✅ Service $(SERVICE_NAME) completely removed$(NC)"

test-service: check-deps ## Run tests for a service (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make test-service SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Testing service: $(SERVICE_NAME)$(NC)"
	@if [ -d "services/$(SERVICE_NAME)" ]; then \
		cd services/$(SERVICE_NAME) && python -m pytest tests/ -v; \
	else \
		echo "$(RED)❌ Service $(SERVICE_NAME) not found$(NC)"; \
		exit 1; \
	fi

logs-service: ## Show logs for a service (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make logs-service SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Showing logs for service: $(SERVICE_NAME)$(NC)"
	kubectl logs -f deployment/$(SERVICE_NAME)-service -n medapp

port-forward: ## Port forward a service for local access (requires SERVICE_NAME)
ifndef SERVICE_NAME
	@echo "$(RED)❌ SERVICE_NAME is required. Usage: make port-forward SERVICE_NAME=my-service$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)Port forwarding service: $(SERVICE_NAME)$(NC)"
	@SERVICE_PORT=$$(cd $(ANSIBLE_DIR) && ansible-playbook playbooks/list-services.yml --limit localhost -e service_name=$(SERVICE_NAME) | grep -oP 'Port: \K\d+' | head -1); \
	if [ -n "$$SERVICE_PORT" ]; then \
		echo "$(GREEN)Forwarding $(SERVICE_NAME) to localhost:$$SERVICE_PORT$(NC)"; \
		kubectl port-forward svc/$(SERVICE_NAME)-service $$SERVICE_PORT:80 -n medapp; \
	else \
		echo "$(RED)❌ Could not determine port for service $(SERVICE_NAME)$(NC)"; \
	fi

status: check-deps ## Show overall system status
	@echo "$(YELLOW)MedApp System Status$(NC)"
	@echo "===================="
	@echo ""
	@echo "$(GREEN)Kubernetes Pods:$(NC)"
	@kubectl get pods -n medapp 2>/dev/null || echo "$(RED)❌ Unable to connect to Kubernetes$(NC)"
	@echo ""
	@echo "$(GREEN)Services:$(NC)"
	@kubectl get svc -n medapp 2>/dev/null || echo "$(RED)❌ Unable to get services$(NC)"
	@echo ""
	@echo "$(GREEN)Docker Images:$(NC)"
	@docker images $(DOCKER_REGISTRY)/medapp-* 2>/dev/null || echo "$(RED)❌ No MedApp images found$(NC)"

clean: ## Clean up Docker images and stopped containers
	@echo "$(YELLOW)Cleaning up Docker resources...$(NC)"
	@docker system prune -f
	@docker image prune -f
	@echo "$(GREEN)✅ Docker cleanup complete$(NC)"

install-deps: ## Install required dependencies (Ubuntu/Debian)
	@echo "$(YELLOW)Installing dependencies...$(NC)"
	@sudo apt-get update
	@sudo apt-get install -y ansible docker.io
	@curl -LO "https://dl.k8s.io/release/$$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
	@sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
	@rm kubectl
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

# Development helpers
dev-setup: setup ## Setup development environment
	@echo "$(YELLOW)Setting up development environment...$(NC)"
	@make create-service SERVICE_NAME=example
	@echo "$(GREEN)✅ Development environment ready$(NC)"
	@echo "$(YELLOW)Try: make build-service SERVICE_NAME=example$(NC)"
