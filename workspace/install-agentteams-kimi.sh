#!/bin/zsh
set -euo pipefail

project_dir="/Users/pengyoutian/Desktop/彭祐天的Github/Wiki_of_Tian/projects/GOAI"
cd "$project_dir"

api_key="$({
  osascript <<'APPLESCRIPT'
set dialogResult to display dialog "请输入 Moonshot / Kimi API Key。密钥只会交给本机 AgentTeams 安装程序。" default answer "" with hidden answer buttons {"取消", "继续安装"} default button "继续安装" cancel button "取消" with title "AgentTeams 配置"
return text returned of dialogResult
APPLESCRIPT
} 2>/dev/null)" || {
  echo "已取消：没有写入或提交 API Key。"
  exit 1
}

if [[ -z "$api_key" ]]; then
  echo "API Key 为空，安装已停止。"
  exit 1
fi

export AGENTTEAMS_LANGUAGE="zh"
export AGENTTEAMS_NON_INTERACTIVE="1"
export AGENTTEAMS_VERSION="v1.2.2"
export AGENTTEAMS_LLM_PROVIDER="openai-compat"
export AGENTTEAMS_OPENAI_BASE_URL="https://api.moonshot.cn/v1"
export AGENTTEAMS_DEFAULT_MODEL="kimi-k2.6"
export AGENTTEAMS_MODEL_CONTEXT_WINDOW="256000"
export AGENTTEAMS_MODEL_MAX_TOKENS="32768"
export AGENTTEAMS_MODEL_REASONING="true"
export AGENTTEAMS_MODEL_VISION="true"
export AGENTTEAMS_EMBEDDING_MODEL=""
export AGENTTEAMS_LLM_API_KEY="$api_key"
export AGENTTEAMS_LOCAL_ONLY="1"
export AGENTTEAMS_ENV_FILE="/Users/pengyoutian/agentteams-manager.env"
export AGENTTEAMS_WORKSPACE_DIR="/Users/pengyoutian/agentteams-manager"

unset api_key

exec bash <(curl -fsSL "https://raw.githubusercontent.com/agentscope-ai/AgentTeams/v1.2.2/install/agentteams-install.sh")
