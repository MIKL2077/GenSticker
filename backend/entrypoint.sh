#!/bin/bash

# 表情包生成器服务启动脚本
# 作者: AI Assistant
# 日期: $(date +%Y-%m-%d)

# 设置脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/meme-generator"
VENV_DIR="$PROJECT_DIR/.venv"
PID_FILE="$PROJECT_DIR/meme_server.pid"
LOG_FILE="$PROJECT_DIR/meme_server.log"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查服务是否已经在运行
check_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0  # 服务正在运行
        else
            # PID文件存在但进程不存在，删除过期的PID文件
            rm -f "$PID_FILE"
            return 1  # 服务未运行
        fi
    fi
    return 1  # 服务未运行
}

# 启动服务
start_server() {
    log_info "正在启动表情包生成器服务..."
    
    # 检查是否已经在运行
    if check_running; then
        log_warning "服务已经在运行中 (PID: $(cat "$PID_FILE"))"
        return 1
    fi
    
    # 检查虚拟环境
    if [ ! -d "$VENV_DIR" ]; then
        log_error "虚拟环境不存在: $VENV_DIR"
        return 1
    fi
    
    # 激活虚拟环境并启动服务（前台运行）
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    log_info "以前台模式启动，日志将输出到标准输出"
    log_info "服务地址: http://0.0.0.0:3001"
    
    exec python -m meme_generator.app
}

# 显示服务状态
show_status() {
    if check_running; then
        PID=$(cat "$PID_FILE")
        log_success "服务正在运行 (PID: $PID)"
        log_info "服务地址: http://0.0.0.0:3001"
        log_info "日志文件: $LOG_FILE"
    else
        log_warning "服务未运行"
    fi
}

# 显示帮助信息
show_help() {
    echo "表情包生成器服务管理脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  start     启动服务"
    echo "  stop      停止服务"
    echo "  restart   重启服务"
    echo "  status    显示服务状态"
    echo "  logs      查看服务日志"
    echo "  help      显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start     # 启动服务"
    echo "  $0 status    # 查看状态"
    echo "  $0 logs      # 查看日志"
}

# 查看日志
show_logs() {
    if [ -f "$LOG_FILE" ]; then
        log_info "显示服务日志 (最后50行):"
        echo "----------------------------------------"
        tail -n 50 "$LOG_FILE"
    else
        log_warning "日志文件不存在: $LOG_FILE"
    fi
}

# 主逻辑
case "${1:-start}" in
    start)
        start_server
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "未知选项: $1"
        show_help
        exit 1
        ;;
esac