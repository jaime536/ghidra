# Ghidra 简体中文界面

在不破坏上游同步能力的前提下，为 Ghidra 提供中文界面。

## 为什么是这个做法

Ghidra **没有任何 i18n 基础设施**：全仓库 `ResourceBundle` 命中 0 处，所有界面文字都是硬编码的
Java 字符串字面量（`new MenuData(` 726 处、`setDescription(` 595 处、`setToolTipText(` 671 处……）。

更关键的是，**很多英文串同时是内部标识符**，不只是显示文本：

- `MenuBarManager` 用 `menuManagers.get("File"/"Edit"/"Window"/"Help")` 决定菜单栏顺序；
- `ToolActions` 用 `action.getFullName()` 作为**快捷键持久化的 key**；
- `ComponentNode` 把窗口标题写进 `.tool` XML（`elem.setAttribute("TITLE", ...)`），并用标题匹配还原布局。

所以**直接把源码里的英文改成中文，会破坏菜单排序、用户快捷键和已保存的工具配置**；而且上游每个
小版本会改动约 100 个含界面文案的文件、约 8000 行，就地翻译等于每次同步都要打一场冲突仗。

因此本项目只在**渲染那一刻**做翻译：

```
上游英文源码（内部标识符全部保持英文）
        │
        ├── generic.i18n.L10N                    唯一新增的框架类：查词典，查不到原样返回
        ├── Ghidra/Extensions/zh-cn-l10n/         词典 + CJK 字体（上游永远不会碰）
        ├── GhidraChinese/help-zh/                帮助页译文（与上游路径一一对应）
        │
        └── 14 个显示层调用点包一层 L10N.tr(...)
```

结果：Java 源码 diff 约 50 行、集中在 14 个文件；99% 的汉化内容位于上游不存在的文件里，
`git merge` 几乎不冲突。未翻译的条目自动显示英文，因此上游新增功能不会出问题。

## 使用

汉化默认**关闭**，同一份构建既是英文版也是中文版：

```bash
ghidraRun -Dghidra.i18n=zh_CN
```

用户可以用 `<用户配置目录>/i18n/zh_CN.properties` 覆盖任意词条，无需重新编译。

## 目录

| 路径 | 作用 |
|---|---|
| `Ghidra/Framework/Gui/src/main/java/generic/i18n/L10N.java` | 翻译器 |
| `Ghidra/Extensions/zh-cn-l10n/data/i18n/zh_CN.properties` | 词典（汉化主战场） |
| `Ghidra/Extensions/zh-cn-l10n/data/zh-cn-l10n.theme.properties` | CJK 字体覆盖 |
| `GhidraChinese/help-zh/` | 帮助页译文 + `manifest.tsv` 基线哈希 |
| `tools/help_zh.py` | 帮助译文的叠加 / 陈旧检测 |
| `tools/check_catalog.py` | 词典体检（CI 会跑） |

> `zh-cn-l10n` 目录名故意用小写：主题默认值按**模块名排序**合并且后者胜出，小写名排在
> `Base`/`Docking`/`Gui`/`Decompiler` 之后，这样就能覆盖它们的字体定义而不用改任何上游文件。

## 补充翻译

1. 带上 dump 开关跑一遍界面，收集所有显示过但没有译文的字符串：

   ```bash
   ghidraRun -Dghidra.i18n=zh_CN -Dghidra.i18n.dump=/tmp/missing.properties
   ```

2. 给 `/tmp/missing.properties` 里的条目填上译文，并入 `zh_CN.properties`。
3. `python3 tools/check_catalog.py Ghidra/Extensions/zh-cn-l10n/data/i18n/zh_CN.properties`

**词典的键中，空格必须转义**：`Save\ As...=另存为...`。不转义的话键会被悄悄截断成 `Save`，
运行时看不出错，只是保持英文——`check_catalog.py` 专门检查这一点。

## 跟随上游升级

**当前基线：`Ghidra_12.1.2_build`（上游稳定发布版 tag）。**

汉化分支直接建立在上游 tag 之上，不跟 `master`——上游 `master` 的 `application.version` 长期是
`12.2` + `release.name=DEV`，处于开发中期，不适合作为出包基线。上游小版本约每季度一次，
补丁版间隔 1～2 周且改动很小（12.1.1→12.1.2 仅 60 文件 / 565 行）。

上游发新稳定版（例如 `Ghidra_12.2_build`）时：

```bash
git fetch upstream --tags
git checkout claude/chinese-gui-upstream-sync-dy7jcm
git merge Ghidra_12.2_build          # 直接并入新 tag
```

冲突只可能出现在那 14 个钩子文件里。合并后：

```bash
python3 tools/help_zh.py check        # 哪些帮助译文的原文变了、哪些页面还没翻
./gradlew -I gradle/support/fetchDependencies.gradle -DnoEclipse
python3 tools/help_zh.py apply        # 帮助译文必须在 indexHelp/buildModuleHelp 之前叠加
./gradlew buildGhidra --parallel
python3 tools/help_zh.py apply --revert
```

最后一步用 `apply --revert`，**不要用 `git checkout -- .`**——那会连同源码钩子一起丢掉。

构建要求由基线 tag 决定，CI 会自动读取，不用手改：12.1.2 要 **JDK 21** + Gradle 8.5+，
而上游 `master`（12.2）已经要 JDK 25 + Gradle 9.1+。

## 自动出包

`.github/workflows/build-ghidra.yml` 有三个 job：

| job | 触发时机 | 作用 |
|---|---|---|
| `localization` | 每次 push | 跑词典体检 + 帮助译文陈旧检测，几秒出结果 |
| `build` | 每次 push | **Linux + Windows 两个平台**并行：抓依赖 → 叠加中文帮助 → `gradle buildGhidra` → 上传 zip |
| `release` | **只在推 tag 时** | 收集两个平台的产物，自动创建 GitHub Release 并附上 zip |

JDK 版本不写死，而是从 `Ghidra/application.properties` 的 `application.java.min` 读出来：

```yaml
- run: echo "JDK_VER=$(awk -F'=' '$1=="application.java.min" {print $2}' Ghidra/application.properties)" >> $GITHUB_ENV
```

所以升级基线（21 → 25）时 CI 会自己跟着变。

**日常**：push 之后到 Actions 页面下载 artifact —— `ghidra-zh-ubuntu-latest` 或
`ghidra-zh-windows-latest`。

**正式发版**：打一个 tag 推上去，Release 会自动生成：

```bash
git tag ghidra-zh-12.1.2-r1
git push origin ghidra-zh-12.1.2-r1
```

产物是标准的 Ghidra 发行包 `build/dist/ghidra_<版本>_<日期>.zip`，解压后 `./ghidraRun` 直接跑。

`buildGhidra` **只产出当前 runner 平台的包**，所以 Linux 包和 Windows 包分别由 matrix 的两条腿产出。

### Windows 构建的几个要点

- **shell 统一为 bash**（workflow 级 `defaults.run.shell`）。Windows runner 默认是 PowerShell，
  那会让读取 JDK 版本的 awk 步骤和 `./gradlew` 都失败；Git Bash 每个 runner 都有，
  而 Gradle wrapper 本身能识别 MSYS。
- **不需要 MSVC 环境预激活**。`GPL/vsconfig.gradle` 会自己用 `vswhere.exe` 找 Visual Studio，
  再从 `vcvarsall.bat` 读出 SDK 版本，所以不用引入第三方的 msvc-dev-cmd action。
  `windows-latest` 自带 VS 的 C++ 工作负载（MSVC + Windows SDK + ATL），正好满足
  `CheckToolChain` 的要求。
- **长路径**。Ghidra 源码树本身就深，构建产物还要再深几层，会撞上 260 字符上限；
  所以 checkout **之前**先 `git config --system core.longpaths true`。
- **Python 用 `actions/setup-python`**，统一调 `python`（Git Bash 里通常没有 `python3`）。
  Gradle 自己会按 `python3 / python / py` 顺序探测，setup-python 保证版本落在
  `application.python.supported` 范围内。
- **`fail-fast: false`**：一个平台挂掉不会连累另一个，Linux 包照常产出。

## 已知边界

- `@PluginInfo` 的插件描述是 Java 注解值，必须是编译期常量，**无法**走运行时钩子，目前保持英文。
- JavaHelp 的全文索引器不做中文分词，中文帮助的“搜索”标签页效果有限（目录导航不受影响）。
- 帮助译文必须显式声明 UTF-8：上游页面多为 `charset=windows-1252`，照抄会乱码。
