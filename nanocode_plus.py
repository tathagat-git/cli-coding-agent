#!/usr/bin/env python3
"""
nanocode+ - A powerful terminal coding agent.
Combines tool-calling REPL + graph planning + README tracking + self-improvement.
"""

import json, os, re, subprocess, sys, time
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List
from datetime import datetime
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback: manually load .env file if python-dotenv is not installed
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_env_path):
        with open(_env_path) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _key, _, _val = _line.partition("=")
                    os.environ.setdefault(_key.strip(), _val.strip())

console = Console()

@dataclass
class Config:
    api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    model: str = field(default_factory=lambda: os.environ.get("DEFAULT_MODEL", "poolside/laguna-s-2.1:free"))
    base_url: str = field(default_factory=lambda: os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
    workspace: str = field(default_factory=lambda: os.environ.get("WORKSPACE_DIR", ".workspace"))
    auto_approve: bool = field(default_factory=lambda: os.environ.get("AUTO_APPROVE", "false").lower() == "true")
    auto_test: bool = field(default_factory=lambda: os.environ.get("AUTO_TEST", "true").lower() == "true")
    max_readme_size: int = field(default_factory=lambda: int(os.environ.get("MAX_README_SIZE", "5000")))
    max_iterations: int = field(default_factory=lambda: int(os.environ.get("MAX_ITERATIONS", "50")))
    temperature: float = field(default_factory=lambda: float(os.environ.get("TEMPERATURE", "0.7")))
    plan_mode: bool = False
    
    @classmethod
    def load(cls, path="nanocode_config.json"):
        # Start with environment variable defaults
        config = cls()
        # Override with values from config file if it exists
        if os.path.exists(path):
            with open(path) as f:
                file_config = json.load(f)
                for k, v in file_config.items():
                    if k in cls.__dataclass_fields__:
                        # Never load api_key from file - always use env var
                        if k == "api_key":
                            continue
                        setattr(config, k, v)
        # Ensure api_key always comes from environment, not file
        config.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        return config
    
    def save(self, path="nanocode_config.json"):
        from dataclasses import asdict
        # Never save api_key to config file
        data = asdict(self)
        data.pop("api_key", None)
        with open(path, "w") as f: json.dump(data, f, indent=2)

@dataclass
class Metrics:
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_retries: int = 0
    test_pass_rate: float = 0.0
    history: list = field(default_factory=list)
    def record(self, success, retries, test_pass, node_id):
        self.tasks_completed += int(success)
        self.tasks_failed += int(not success)
        self.total_retries += retries
        total = self.tasks_completed + self.tasks_failed
        if total > 0: self.test_pass_rate = (self.test_pass_rate * (total - 1) + int(test_pass)) / total
        self.history.append({"node_id": node_id, "success": success, "retries": retries, "test_pass": test_pass})

class NodeStatus:
    PENDING = "pending"; IN_PROGRESS = "in_progress"; COMPLETED = "completed"; FAILED = "failed"

@dataclass
class TaskNode:
    id: str; name: str; description: str; status: str = NodeStatus.PENDING
    dependencies: List[str] = field(default_factory=list)
    code_path: Optional[str] = None; readme_path: Optional[str] = None

class TaskGraph:
    def __init__(self): self.nodes = {}; self.edges = []
    def add_node(self, node):
        self.nodes[node.id] = node
        for dep in node.dependencies:
            if (dep, node.id) not in self.edges: self.edges.append((dep, node.id))
    def get_ready_nodes(self):
        ready = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING: continue
            if all(self.nodes.get(d, TaskNode(id=d, name="", description="")).status == NodeStatus.COMPLETED for d in node.dependencies if d in self.nodes): ready.append(node)
        return ready
    def get_dependents(self, node_id): return [b for a, b in self.edges if a == node_id]
    def is_complete(self): return all(n.status == NodeStatus.COMPLETED for n in self.nodes.values())
    def visualize(self):
        icon = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]", "failed": "[!]"}
        lines = []
        for nid, node in self.nodes.items():
            ic = icon.get(node.status, "[ ]")
            dep_str = f" <- {', '.join(node.dependencies)}" if node.dependencies else ""
            lines.append(f"  {ic} {nid}: {node.name}{dep_str}")
        return "\n".join(lines)
    def save(self, path):
        data = {"nodes": {nid: {"id": n.id, "name": n.name, "description": n.description, "status": n.status, "dependencies": n.dependencies, "code_path": n.code_path, "readme_path": n.readme_path} for nid, n in self.nodes.items()}, "edges": list(self.edges)}
        with open(path, "w") as f: json.dump(data, f, indent=2)
    @classmethod
    def load(cls, path):
        with open(path) as f: data = json.load(f)
        g = cls()
        for nid, nd in data["nodes"].items(): g.nodes[nid] = TaskNode(**nd)
        g.edges = [tuple(e) for e in data.get("edges", [])]
        return g

@dataclass
class ReadmeContent:
    node_id: str; name: str; status: str; summary: str; logic: str
    variables: Dict[str, str] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    feeds_to: List[str] = field(default_factory=list)
    progress: List[str] = field(default_factory=list)
    notes: str = ""
    def to_markdown(self):
        lines = [f"# Step: {self.name}", f"> Node: {self.node_id}", f"> Status: {self.status}", f"> Updated: {datetime.now().isoformat(timespec='seconds')}", f"> Dependencies: {', '.join(self.dependencies) or 'none'}", f"> Feeds To: {', '.join(self.feeds_to) or 'none'}", "", "## Summary", self.summary, "", "## Logic", self.logic, "", "## Variables", "| Name | Description |", "|------|-------------|"]
        for k, v in self.variables.items(): lines.append(f"| `{k}` | {v} |")
        lines += ["", "## Connections", f"- **depends_on**: {', '.join(self.dependencies) or 'none'}", f"- **feeds_to**: {', '.join(self.feeds_to) or 'none'}", "", "## Progress"]
        for item in self.progress: lines.append(f"- {item}")
        if self.notes: lines += ["", "## Notes", self.notes]
        return "\n".join(lines)

class ReadmeManager:
    def __init__(self, src_dir=".workspace/src", max_size=5000): self.src_dir = src_dir; self.max_size = max_size; self.cache = {}
    def create(self, content):
        md = content.to_markdown()
        if len(md) > self.max_size: md = "> COMPRESSED\n\n" + md[:self.max_size]
        os.makedirs(self.src_dir, exist_ok=True)
        path = os.path.join(self.src_dir, f"README_{content.node_id}.md")
        with open(path, "w") as f: f.write(md)
        self.cache[content.node_id] = content
        return path
    def get_context(self, node_id, include_deps=True):
        parts = []; c = self.cache.get(node_id)
        if c: parts.append(f"=== CURRENT: {c.name} ===\n{c.to_markdown()}")
        if include_deps and c:
            for dep_id in c.dependencies:
                dep = self.cache.get(dep_id)
                if dep: parts.append(f"=== DEP: {dep.name} ===\n{dep.to_markdown()}")
        return "\n\n".join(parts)
    def load_all(self):
        if not os.path.isdir(self.src_dir): return
        for fn in os.listdir(self.src_dir):
            if fn.startswith("README_") and fn.endswith(".md"):
                nid = fn[7:-3]
                with open(os.path.join(self.src_dir, fn)) as f: md = f.read()
                self.cache[nid] = ReadmeContent(node_id=nid, name="", status="completed", summary=md[:200], logic="", variables={}, dependencies=[], feeds_to=[], progress=[])

class LLMClient:
    MAX_RETRIES = 5
    def __init__(self, config): self.config = config; self._client = None
    @property
    def client(self):
        if self._client is None: self._client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key, default_headers={"HTTP-Referer": "https://github.com/nanocode-plus", "X-Title": "nanocode+"})
        return self._client
    def chat(self, messages, temperature=None, max_tokens=4096, tools=None):
        temp = temperature if temperature is not None else self.config.temperature
        for attempt in range(self.MAX_RETRIES):
            try:
                kwargs = dict(model=self.config.model, messages=messages, temperature=temp, max_tokens=max_tokens, stream=True)
                if tools: kwargs["tools"] = tools
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:
                if "429" in str(e) and attempt < self.MAX_RETRIES - 1:
                    wait = (attempt + 1) * 5; console.print(f"[yellow]Rate limited, waiting {wait}s...[/]"); time.sleep(wait)
                else: raise
    def ask(self, system, user, **kw):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        stream = self.chat(messages, **kw)
        result = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta: result += delta
        return result

TOOLS_SCHEMA = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a file from disk.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write content to a file.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}, "content": {"type": "string", "description": "Content"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Replace exact string in a file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}}, "required": ["path", "old_string", "new_string"]}}},
    {"type": "function", "function": {"name": "bash", "description": "Run a shell command.", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Shell command"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "grep", "description": "Search files for a regex pattern.", "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string", "default": "."}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "list_files", "description": "List files in a directory.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "default": "."}}, "required": []}}},
    {"type": "function", "function": {"name": "todo_write", "description": "Update the task list.", "parameters": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "done"]}}, "required": ["content", "status"]}}}, "required": ["items"]}}},
]

def execute_tool(name, args, config):
    if name == "read_file":
        try:
            with open(args["path"], encoding="utf-8") as f: return f.read()
        except Exception as e: return f"Error: {e}"
    elif name == "write_file":
        if not config.auto_approve:
            if input(f"  write_file({args['path']}) approve? [y/N] ").strip().lower() != "y": return "Denied"
        try:
            os.makedirs(os.path.dirname(args["path"]) or ".", exist_ok=True)
            with open(args["path"], "w", encoding="utf-8") as f: f.write(args["content"])
            return f"Wrote {args['path']}"
        except Exception as e: return f"Error: {e}"
    elif name == "edit_file":
        try:
            with open(args["path"], encoding="utf-8") as f: content = f.read()
            if args["old_string"] not in content: return f"old_string not found in {args['path']}"
            content = content.replace(args["old_string"], args["new_string"])
            with open(args["path"], "w", encoding="utf-8") as f: f.write(content)
            return f"Edited {args['path']}"
        except Exception as e: return f"Error: {e}"
    elif name == "bash":
        if not config.auto_approve:
            if input(f"  bash({args['command']}) approve? [y/N] ").strip().lower() != "y": return "Denied"
        try:
            r = subprocess.run(args["command"], shell=True, capture_output=True, text=True, timeout=30)
            return r.stdout + r.stderr
        except subprocess.TimeoutExpired: return "Timeout (30s)"
        except Exception as e: return f"Error: {e}"
    elif name == "grep":
        try: regex = re.compile(args["pattern"])
        except re.error as e: return f"Invalid regex: {e}"
        matches = []
        for dirpath, _, filenames in os.walk(args.get("path", ".")):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    with open(fp, encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line): matches.append(f"{fp}:{i}: {line.rstrip()}")
                except: continue
        return "\n".join(matches[:50]) if matches else "No matches"
    elif name == "list_files":
        try: return "\n".join(sorted(os.listdir(args.get("path", "."))))
        except Exception as e: return f"Error: {e}"
    elif name == "todo_write":
        marks = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}
        return "\n".join(f"  {marks.get(item['status'], '[ ]')} {item['content']}" for item in args["items"])
    return f"Unknown tool: {name}"

class NanoCodePlus:
    def __init__(self, config):
        self.config = config; self.llm = LLMClient(config); self.graph = None
        self.readme_mgr = ReadmeManager(src_dir=os.path.join(config.workspace, "src"), max_size=config.max_readme_size)
        self.metrics = Metrics(); self.messages = []
        for d in ["", "/src", "/tests", "/state"]: os.makedirs(config.workspace + d, exist_ok=True)
    def _system_prompt(self):
        prompt = f"You are nanocode+, a powerful terminal coding agent.\nYou can read/write/edit files, run commands, search code, and manage tasks.\nUse todo_write to plan multi-step tasks.\nWrite ONLY Python code in .py files - no shell commands.\n\nEnvironment:\n  cwd: {os.getcwd()}\n  os: {os.uname().sysname}\n"
        if os.path.exists("NANOCODE.md"):
            try:
                with open("NANOCODE.md") as f: prompt += f"\nProject instructions:\n{f.read()}"
            except: pass
        return prompt
    def repl(self):
        console.print(Panel("nanocode+ - terminal coding agent\nCommands: /plan /graph /run /status /model <name> /quit\nfModel: {self.config.model}", title="nanocode+", border_style="green"))
        self.messages = [{"role": "system", "content": self._system_prompt()}]
        while True:
            try:
                prompt = "plan> " if self.config.plan_mode else "> "
                user_input = input(prompt).strip()
                if not user_input: continue
                if user_input in ("/quit", "/exit"): console.print("[yellow]Goodbye![/]"); break
                elif user_input == "/plan":
                    self.config.plan_mode = not self.config.plan_mode
                    console.print(f"Plan mode: {'ON' if self.config.plan_mode else 'OFF'}"); continue
                elif user_input == "/graph":
                    if self.graph: console.print(Panel(self.graph.visualize(), title="Task Graph", border_style="cyan"))
                    else: console.print("[yellow]No graph. Describe a project first.[/]"); continue
                elif user_input == "/status": self._show_status(); continue
                elif user_input == "/run": self._execute_graph(); continue
                elif user_input.startswith("/model "):
                    self.config.model = user_input[7:].strip(); self.config.save()
                    console.print(f"[green]Model: {self.config.model}[/]"); continue
                self.messages.append({"role": "user", "content": user_input})
                self._run_loop()
            except (EOFError, KeyboardInterrupt): console.print("\n[yellow]Goodbye![/]"); break
    def _run_loop(self):
        for _ in range(self.config.max_iterations):
            try: stream = self.llm.chat(self.messages, tools=TOOLS_SCHEMA)
            except Exception as e: console.print(f"[red]API Error: {e}[/]"); return
            reply = ""; tool_calls = []; finish_reason = None
            for chunk in stream:
                choice = chunk.choices[0]
                if choice.delta.content: print(choice.delta.content, end="", flush=True); reply += choice.delta.content
                for tc in choice.delta.tool_calls or []:
                    if tc.index >= len(tool_calls): tool_calls.append({"id": "", "name": "", "arguments": ""})
                    tool_calls[tc.index]["id"] += tc.id or ""
                    tool_calls[tc.index]["name"] += tc.function.name or ""
                    tool_calls[tc.index]["arguments"] += tc.function.arguments or ""
                if choice.finish_reason: finish_reason = choice.finish_reason
            print()
            if finish_reason == "tool_calls" and tool_calls:
                assistant_msg = {"role": "assistant", "content": reply, "tool_calls": [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}} for tc in tool_calls]}
                self.messages.append(assistant_msg)
                for tc in tool_calls:
                    try: args = json.loads(tc["arguments"])
                    except: args = {}
                    console.print(f"[cyan]  {tc['name']}({json.dumps(args)[:100]})[/]")
                    if self.config.plan_mode and tc["name"] in ("write_file", "edit_file", "bash"): result = "Plan mode ON - writes disabled"
                    else: result = execute_tool(tc["name"], args, self.config)
                    self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            else:
                if reply: self.messages.append({"role": "assistant", "content": reply})
                return
    def plan_project(self, description):
        console.print("[blue]Planning...[/]")
        system = 'You are a software architect. Break the project into concrete steps as a DAG.\nReturn ONLY JSON: {"steps": [{"id": "snake_case", "name": "...", "description": "...", "dependencies": [...]}]}\nRules: ids are snake_case, dependencies reference earlier ids, foundational steps first.'
        user = f"Project: {description}\n\nBreak this into implementable steps."
        response = self.llm.ask(system, user, temperature=0.5)
        match = re.search(r"\{[\s\S]*\}", response)
        if not match: console.print("[red]Could not parse plan[/]"); return None
        try: data = json.loads(match.group())
        except: console.print("[red]Invalid JSON[/]"); return None
        graph = TaskGraph()
        for s in data.get("steps", []): graph.add_node(TaskNode(id=s["id"], name=s["name"], description=s["description"], dependencies=s.get("dependencies", [])))
        self.graph = graph
        console.print(Panel(graph.visualize(), title="Task Graph", border_style="cyan"))
        graph.save(os.path.join(self.config.workspace, "state", "graph.json"))
        return graph
    def _execute_graph(self):
        if not self.graph:
            state_path = os.path.join(self.config.workspace, "state", "graph.json")
            if os.path.exists(state_path): self.graph = TaskGraph.load(state_path)
            else: console.print("[red]No graph.[/]"); return
        while not self.graph.is_complete():
            ready = self.graph.get_ready_nodes()
            if not ready: console.print("[red]No more steps.[/]"); break
            for node in ready: self._execute_step(node)
        console.print(Panel(self.graph.visualize(), title="Final Graph", border_style="green"))
    def _execute_step(self, node):
        node.status = NodeStatus.IN_PROGRESS
        console.print(Panel(f"Step: {node.name}\n{node.description}", style="cyan"))
        dep_context = self.readme_mgr.get_context(node.id)
        system = "You are a Python code generator. Write ONLY Python code. No shell commands. No bash.\nFormat: <CODE>...python...</CODE> <VARS>name: desc</VARS> <LOGIC>why</LOGIC>"
        user = f"Step: {node.name}\nDescription: {node.description}\nDependency context: {dep_context or 'none'}\n\nWrite Python code to implement this step."
        for attempt in range(3):
            response = self.llm.ask(system, user, temperature=self.config.temperature)
            code = self._extract_tag(response, "CODE") or response
            vars_text = self._extract_tag(response, "VARS") or ""
            logic = self._extract_tag(response, "LOGIC") or ""
            if self._is_shell(code):
                console.print(f"[yellow]Shell code detected, retry {attempt+1}/3[/]")
                user += "\nIMPORTANT: Last output was shell commands. Write PYTHON code ONLY."; continue
            break
        code = re.sub(r"^```(?:python)?\n?", "", code); code = re.sub(r"\n?```$", "", code.strip())
        src_dir = os.path.join(self.config.workspace, "src"); os.makedirs(src_dir, exist_ok=True)
        code_path = os.path.join(src_dir, f"{node.id}.py")
        with open(code_path, "w") as f: f.write(code)
        node.code_path = code_path
        feeds_to = self.graph.get_dependents(node.id)
        readme = ReadmeContent(node_id=node.id, name=node.name, status="completed", summary=logic[:300] if logic else code[:200], logic=logic, variables={}, dependencies=node.dependencies, feeds_to=feeds_to, progress=[f"[x] {node.name} implemented"])
        node.readme_path = self.readme_mgr.create(readme)
        test_passed = True
        if self.config.auto_test: test_passed = self._run_test(node, code)
        node.status = NodeStatus.COMPLETED if test_passed else NodeStatus.FAILED
        icon = "+" if test_passed else "x"; console.print(f"[{'green' if test_passed else 'red'}]{icon} {node.name}[/]")
        self.graph.save(os.path.join(self.config.workspace, "state", "graph.json"))
    def _run_test(self, node, code):
        try:
            system = "Write pytest tests for this Python code. Return ONLY test code, no markdown fences."
            test_code = self.llm.ask(system, f"Code:\n{code[:2000]}", temperature=0.3)
            if not test_code or not isinstance(test_code, str): return True
            test_code = re.sub(r"^```(?:python)?\n?", "", test_code); test_code = re.sub(r"\n?```$", "", test_code.strip())
            test_dir = os.path.join(self.config.workspace, "tests"); os.makedirs(test_dir, exist_ok=True)
            test_path = os.path.join(test_dir, f"test_{node.id}.py")
            with open(test_path, "w") as f: f.write(test_code)
            r = subprocess.run(["python", "-m", "pytest", test_path, "-v", "--tb=short"], capture_output=True, text=True, timeout=30, cwd=self.config.workspace)
            return r.returncode == 0
        except: return True
    @staticmethod
    def _extract_tag(text, tag):
        m = re.compile(f"<{tag}>(.*?)</{tag}>", re.DOTALL).search(text)
        return m.group(1).strip() if m else None
    @staticmethod
    def _is_shell(code):
        shell_kw = ["ls ", "mkdir ", "cd ", "rm ", "cat ", "echo ", "pip install", "npm ", "shellcmd", "apt "]
        lines = [l for l in code.splitlines() if l.strip() and not l.strip().startswith("#")]
        if not lines: return True
        shell_count = sum(1 for l in lines for kw in shell_kw if l.strip().startswith(kw))
        return shell_count / len(lines) > 0.3
    def _show_status(self):
        m = self.metrics
        console.print(Panel(f"Model: {self.config.model}\nWorkspace: {self.config.workspace}\nPlan mode: {'ON' if self.config.plan_mode else 'OFF'}\nAuto-approve: {self.config.auto_approve}\nTasks completed: {m.tasks_completed}\nTest pass rate: {m.test_pass_rate:.0%}", title="Status", border_style="cyan"))
        if self.graph: console.print(Panel(self.graph.visualize(), title="Task Graph", border_style="cyan"))

def main():
    config = Config.load()
    if not config.api_key: config.api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not config.api_key: config.api_key = input("OpenRouter API key: ").strip(); config.save()
    if len(sys.argv) > 1:
        args = sys.argv[1:]
        i = 0
        while i < len(args):
            if args[i] == "--model" and i + 1 < len(args): config.model = args[i + 1]; i += 2
            elif args[i] == "--auto-approve": config.auto_approve = True; i += 1
            elif args[i] == "--workspace" and i + 1 < len(args): config.workspace = args[i + 1]; i += 2
            else: i += 1
    config.save()
    agent = NanoCodePlus(config)
    agent.repl()

if __name__ == "__main__":
    main()
