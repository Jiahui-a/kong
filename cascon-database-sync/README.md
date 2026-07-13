# Cascon 芯片测试文件夹同步工具

将各同事本地 Cascon 项目中的芯片测试文件夹，按 `database.xlsx` 中的**型号 / 位号 / 料号**映射关系，**复制**到公盘 `database` 目录。重命名**仅发生在公盘副本上**，各同事本地项目中的原始文件夹**不会被修改**。

## 背景

- 每位同事的 Cascon 项目目录结构相近，但芯片测试文件夹命名不一致
- `database.xlsx` 记录各芯片的型号、位号、料号对应关系
- 公盘需要统一存放所有芯片测试数据，且命名规范一致
- 芯片文件夹内通常还存在与文件夹同名的文件或子文件夹，也需要一并重命名

## 功能

1. 读取 `database.xlsx`（必需列：**型号**、**位号**、**料号**）
2. 扫描一个或多个本地项目目录，自动识别芯片测试文件夹（**只读，不修改本地**）
3. 根据位号 / 料号 / 型号等信息匹配 `database` 记录
4. **复制**到公盘，并将公盘上的文件夹重命名为 `[型号 料号]`
5. 将公盘副本内与原始文件夹同名的文件、子文件夹也重命名为 `[型号 料号]`

> **重要**：本地源文件夹始终保持原名（如 `U1`），所有重命名操作仅作用于公盘 `--output` 目录中的副本。

## 安装

```bash
cd cascon-database-sync
pip install -r requirements.txt
```

## database.xlsx 格式

| 型号 | 位号 | 料号 |
|------|------|------|
| STM32F103C8T6 | U1 | C12345-001 |
| GD32F303CCT6 | U2 | C12345-002 |

可使用模板生成脚本：

```bash
python scripts/create_template.py
```

模板输出路径：`templates/database_template.xlsx`

## 使用方法

### 命令行

```bash
python -m cascon_sync \
  --database ./database.xlsx \
  --source /path/to/project_a /path/to/project_b \
  --output /path/to/public/database
```

常用参数：

| 参数 | 说明 |
|------|------|
| `-d, --database` | database.xlsx 路径 |
| `-s, --source` | 一个或多个项目根目录 |
| `-o, --output` | 公盘 database 输出目录 |
| `--recursive` | 递归扫描子目录（默认只扫描项目根下一级） |
| `--dry-run` | 预览模式，不实际复制 |
| `--overwrite` | 目标已存在时覆盖 |
| `--json-report` | 输出 JSON 格式同步报告 |
| `-c, --config` | 使用 YAML 配置文件 |

### 预览（推荐先执行）

```bash
python -m cascon_sync \
  -d ./database.xlsx \
  -s "D:\Cascon\ProjectA" \
  -o "Z:\database" \
  --dry-run
```

### 配置文件

复制 `config.example.yaml` 并修改路径后：

```bash
python -m cascon_sync -c config.yaml
```

## 匹配规则

工具会按以下顺序尝试将文件夹名与 `database` 记录匹配：

1. **精确匹配**：位号、料号、型号，或常见组合（如 `U1_C12345-001`）
2. **拆分匹配**：按下划线、连字符、空格拆分文件夹名后逐段匹配
3. **包含匹配**：文件夹名中包含位号或料号时匹配（优先更长料号，减少误匹配）

若文件夹无法匹配，会在报告中列出，便于补充 `database.xlsx` 或调整命名。

## 重命名示例

假设本地项目文件夹名为 `U1`（**本地保持 `U1` 不变**），`database` 中对应：

- 型号：`STM32F103C8T6`
- 料号：`C12345-001`

同步后：

**本地（不变）：**
```text
D:\Cascon\ProjectA\U1\
  U1\
  U1.xlsx
  readme.txt
```

**公盘（重命名）：**
```text
Z:\database\
  [STM32F103C8T6 C12345-001]\
    [STM32F103C8T6 C12345-001]        # 原 U1 同名子文件夹
    [STM32F103C8T6 C12345-001].xlsx   # 原 U1.xlsx
    readme.txt                        # 其他文件保持不变
```

## 项目结构

```text
cascon-database-sync/
├── cascon_sync/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py          # 命令行入口
│   ├── database.py     # 读取 database.xlsx
│   ├── matcher.py      # 文件夹匹配逻辑
│   └── sync.py         # 复制与重命名
├── scripts/
│   └── create_template.py
├── templates/
│   └── database_template.xlsx
├── tests/
│   └── test_sync.py
├── config.example.yaml
├── requirements.txt
└── README.md
```

## 注意事项

- 建议先使用 `--dry-run` 确认匹配结果
- 默认不覆盖已存在的目标文件夹，需覆盖时加 `--overwrite`
- 公盘路径请确保有写入权限
- Windows 下路径可使用 `Z:\database` 等形式
