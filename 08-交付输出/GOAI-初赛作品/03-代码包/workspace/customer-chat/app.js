const params = new URLSearchParams(window.location.search);
const id = params.get("conversation_id") || "linked-demo-conversation";
const customer = params.get("customer_id") || "C001";
const messages = document.querySelector("#messages");
const status = document.querySelector("#status");
const presence = document.querySelector("#presence");
const composer = document.querySelector("#composer");
const input = document.querySelector("#message");
const sendButton = document.querySelector("#send-button");

function formatTime(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function render(items) {
  if (!items.length) return;
  const rows = items.map((message) => {
    const row = document.createElement("article");
    row.classList.add("message-row");
    row.classList.add(message.sender === "CUSTOMER" ? "customer" : "frontline");

    const bubble = document.createElement("div");
    bubble.classList.add("message-bubble");
    bubble.textContent = message.body;

    const meta = document.createElement("span");
    meta.classList.add("message-meta");
    const sender = message.sender === "CUSTOMER" ? "您" : "酒店服务助手";
    meta.textContent = `${sender} · ${formatTime(message.occurred_at)}`;

    row.append(bubble, meta);
    return row;
  });
  messages.replaceChildren(...rows);
  messages.scrollTop = messages.scrollHeight;
}

async function refresh() {
  try {
    const query = new URLSearchParams({customer_id: customer});
    const response = await fetch(`/conversations/${encodeURIComponent(id)}?${query}`);
    if (!response.ok) {
      presence.textContent = response.status === 404 ? "等待服务会话" : "连接异常";
      return;
    }
    const projection = await response.json();
    render(projection.messages);
    messages.setAttribute("aria-busy", "false");
    presence.textContent = "在线";
  } catch (error) {
    presence.textContent = "暂时无法连接";
  }
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = input.value.trim();
  if (!body) return;

  sendButton.disabled = true;
  status.classList.remove("error");
  status.textContent = "发送中…";
  try {
    const response = await fetch(`/conversations/${encodeURIComponent(id)}/messages`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({sender: "CUSTOMER", customer_id: customer, body}),
    });
    if (!response.ok) throw new Error("send failed");
    composer.reset();
    status.textContent = "已发送";
    await refresh();
  } catch (error) {
    status.classList.add("error");
    status.textContent = "发送失败，请稍后重试";
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
});

refresh();
window.setInterval(refresh, 1500);
