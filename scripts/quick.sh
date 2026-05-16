#!/bin/bash
# SENTINEL — Quick Reference Commands

echo "🎯 SENTINEL Quick Commands"
echo "=========================="
echo ""

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: Run this from the sentinel/ directory"
    exit 1
fi

show_menu() {
    echo "Choose an action:"
    echo ""
    echo "  1) 🚀 Full startup (data + models + all services)"
    echo "  2) 🔄 Restart all services"
    echo "  3) 🛑 Stop all services"
    echo "  4) 🗑️  Reset everything (including data)"
    echo "  5) 📊 View logs"
    echo "  6) 🧪 Run tests"
    echo "  7) 📈 Start transaction replay"
    echo "  8) 🌐 Open dashboard"
    echo "  9) 📋 Show service status"
    echo "  0) ❌ Exit"
    echo ""
    read -p "Enter choice [0-9]: " choice
    
    case $choice in
        1)
            echo "🚀 Starting full stack..."
            bash scripts/start_all.sh
            ;;
        2)
            echo "🔄 Restarting services..."
            docker compose restart
            ;;
        3)
            echo "🛑 Stopping services..."
            docker compose down
            ;;
        4)
            read -p "⚠️  This will delete all data. Continue? (y/N): " confirm
            if [ "$confirm" = "y" ]; then
                docker compose down -v
                echo "✅ All data removed"
            fi
            ;;
        5)
            echo "📊 Available services:"
            echo "  - orchestrator"
            echo "  - frontend"
            echo "  - kafka"
            echo "  - redis"
            echo "  - neo4j"
            echo "  - postgres"
            echo "  - mlflow"
            read -p "Enter service name: " service
            docker compose logs -f $service
            ;;
        6)
            echo "🧪 Running tests..."
            python3 -m pytest tests/agents/ tests/scenarios/ -v
            ;;
        7)
            echo "📈 Starting transaction replay..."
            python3 data/generators/replay.py
            ;;
        8)
            echo "🌐 Opening dashboard..."
            open http://localhost:3000 || xdg-open http://localhost:3000
            ;;
        9)
            echo "📋 Service Status:"
            docker compose ps
            echo ""
            echo "🌐 Access Points:"
            echo "  Frontend:     http://localhost:3000"
            echo "  Orchestrator: http://localhost:8000"
            echo "  MLflow:       http://localhost:5050"
            echo "  Neo4j:        http://localhost:7474"
            ;;
        0)
            echo "👋 Goodbye!"
            exit 0
            ;;
        *)
            echo "❌ Invalid choice"
            ;;
    esac
    
    echo ""
    read -p "Press Enter to continue..."
    show_menu
}

show_menu
