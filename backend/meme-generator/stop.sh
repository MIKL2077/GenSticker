#!/bin/bash

# 表情包生成器服务停止脚本
# 作者: AI Assistant
# 日期: $(date +%Y-%m-%d)

# 设置脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
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

# 检查服务是否在运行
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

# 停止服务
stop_server() {
    log_info "正在停止表情包生成器服务..."
    
    if ! check_running; then
        log_warning "服务未运行"
        return 0
    fi
    
    PID=$(cat "$PID_FILE")
    log_info "找到服务进程 (PID: $PID)"
    
    # 尝试优雅停止
    log_info "发送SIGTERM信号..."
    kill -TERM "$PID" 2>/dev/null
    
    # 等待进程结束
    local count=0
    while [ $count -lt 10 ]; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            log_success "服务已成功停止"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
        count=$((count + 1))
        log_info "等待服务停止... ($count/10)"
    done
    
    # 如果优雅停止失败，强制停止
    log_warning "优雅停止失败，尝试强制停止..."
    kill -KILL "$PID" 2>/dev/null
    
    sleep 1
    
    if ! ps -p "$PID" > /dev/null 2>&1; then
        log_success "服务已强制停止"
        rm -f "$PID_FILE"
    else
        log_error "无法停止服务 (PID: $PID)"
        return 1
    fi
}

# 显示服务状态
show_status() {
    if check_running; then
        PID=$(cat "$PID_FILE")
        log_success "服务正在运行 (PID: $PID)"
    else
        log_warning "服务未运行"
    fi
}

# 显示帮助信息
show_help() {
    echo "表情包生成器服务停止脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  stop      停止服务"
    echo "  status    显示服务状态"
    echo "  help      显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 stop      # 停止服务"
    echo "  $0 status    # 查看状态"
}

# 主逻辑
case "${1:-stop}" in
    stop)
        stop_server
        ;;
    status)
        show_status
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