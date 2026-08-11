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

**发行包开箱即中文**，直接运行 `ghidraRun`（Windows 为 `ghidraRun.bat`）即可。

想要英文界面，把 `support/launch.properties` 里这一行改成 `off`（或删掉）：

```properties
VMARGS=-Dghidra.i18n=zh_CN
```

同一份构建既是中文版也是英文版，改的只是发行包的默认值。

> ### ⚠️ 命令行上加 `-D` 是无效的
>
> `ghidraRun -Dghidra.i18n=zh_CN` **不起作用**，界面仍是英文。
>
> `ghidraRun` 把命令行参数原样透传给 `support/launch.sh`，而后者最终拼成：
>
> ```
> java <VMARGS...> -cp <classpath> ghidra.Ghidra ghidra.GhidraRun <你的参数>
> ```
>
> 你的参数落在**类名之后**——那是给程序的参数，JVM 根本不解析，
> 于是 `System.getProperty("ghidra.i18n")` 为 null。`ghidraRun.bat` 的 `%*` 同理。
>
> 能真正送进 JVM 的只有两条路，它们都拼在类名之前：
>
> | 方式 | 怎么用 |
> |---|---|
> | `support/launch.properties` | 加 `VMARGS=-Dghidra.i18n=zh_CN`（发行包已内置） |
> | 环境变量 | `GHIDRA_JAVA_OPTIONS=-Dghidra.i18n=zh_CN ./ghidraRun` |

用户还可以用 `<用户配置目录>/i18n/zh_CN.properties` 覆盖任意词条，无需重新编译。

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
   GHIDRA_JAVA_OPTIONS="-Dghidra.i18n=zh_CN -Dghidra.i18n.dump=/tmp/missing.properties" ./ghidraRun
   ```

2. 给 `/tmp/missing.properties` 里的条目填上译文，并入 `zh_CN.properties`。
3. `python3 tools/check_catalog.py Ghidra/Extensions/zh-cn-l10n/data/i18n/zh_CN.properties`

**词典的键中，空格必须转义**：`Save\ As...=另存为...`。不转义的话键会被悄悄截断成 `Save`，
运行时看不出错，只是保持英文——`check_catalog.py` 专门检查这一点。

## 跟随上游升级

### 分支

| 分支 | 作用 |
|---|---|
| **`chinese`** | **汉化主线**，日常开发与发版都在这里 |
| `master` | 上游纯净镜像，只做 `git merge upstream/master`，**永不放汉化提交** |

两条线**血缘不同**，这是有意为之：`chinese` 建立在上游**稳定发布版 tag** 之上，
而 `master` 跟的是上游 `master`。所以**不要把汉化并进 `master`**——那会把基线拖回
`12.2` + `release.name=DEV` 的开发中期版本，也会毁掉 `master` 作为干净镜像的价值。

**当前基线：`Ghidra_12.1.2_build`。** 上游小版本约每季度一次，补丁版间隔 1～2 周且改动
很小（12.1.1→12.1.2 仅 60 文件 / 565 行）。

上游发新稳定版（例如 `Ghidra_12.2_build`）时：

```bash
git fetch upstream --tags
git checkout chinese
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
| `build` | 每次 push | **Linux + Windows + macOS 三个平台**并行：抓依赖 → 叠加中文帮助 → `gradle buildGhidra` → 上传 zip |
| `release` | **只在推 tag 时** | 收集各平台产物，自动创建 GitHub Release 并附上 zip |

实测耗时（12.1.2 基线）：Linux 约 9 分半，macOS 约 12 分半，Windows 约 13 分半。
三条腿并行，所以一次完整发版约 18 分钟（以最慢的 Windows 为准）。

JDK 版本不写死，而是从 `Ghidra/application.properties` 的 `application.java.min` 读出来：

```yaml
- run: echo "JDK_VER=$(awk -F'=' '$1=="application.java.min" {print $2}' Ghidra/application.properties)" >> $GITHUB_ENV
```

所以升级基线（21 → 25）时 CI 会自己跟着变。

**日常 push 不会产生 Release**，只有 Actions artifact —— 到 Actions 页面下载
`ghidra-zh-ubuntu-latest` / `ghidra-zh-windows-latest` / `ghidra-zh-macos-latest`。
artifact 保留 90 天。

**正式发版（推荐：网页操作，不需要命令行）**：

> GitHub 网页 → **Actions** → 左侧 **Build Ghidra** → 右上 **Run workflow**
> → 在 **发版 tag** 填版本号（如 `ghidra-zh-12.1.2-r2`）→ **Run workflow**

约 18 分钟后 Releases 页面就会出现新版本，附带三个平台的安装包（附件长期保留）。
**留空则只构建、不发版。**

tag 由 workflow 自己创建，用的是 Actions 的 `GITHUB_TOKEN`。这样发版完全不需要本地克隆。
（用 `GITHUB_TOKEN` 推的 tag 不会再触发新的 workflow run，GitHub 明确防止此类递归，
所以不会出现「发版→构建→再发版」的循环。）

如果你有本地克隆，直接推 tag 也一样会发版：

```bash
git tag ghidra-zh-12.1.2-r2 && git push origin ghidra-zh-12.1.2-r2
```

产物是标准的 Ghidra 发行包，解压后运行 `ghidraRun`（Windows 为 `ghidraRun.bat`）
即为中文界面，无需额外参数。

### 某个平台构建失败时会怎样

**照发不误，但会明确标注缺了哪个平台。** `release` job 用的是
`if: always() && startsWith(github.ref, 'refs/tags/')`——如果只写 `needs: build`，
Actions 默认要求**所有** matrix 腿都成功，那么任何一个平台挂掉就一个包都发不出来，
这与 `fail-fast: false` 的初衷正好相反。

`tools/release_notes.py` 会检查实际收集到的安装包：平台名直接从文件名解析
（`buildGhidra` 产出的是 `ghidra_<版本>_<日期>_<平台>.zip`，见
`gradle/root/distribution.gradle` 的 `archiveFileName`），在 Release 说明里列出包含哪些、
并对缺失的平台打出醒目警告。**如果一个包都没有，它会直接报错**，不会发出空 Release。

`buildGhidra` **只产出当前 runner 平台的包**，所以三个平台的包分别由 matrix 的三条腿产出。

### Windows 构建的几个要点

- **shell 统一为 bash**（workflow 级 `defaults.run.shell`）。Windows runner 默认是 PowerShell，
  那会让读取 JDK 版本的 awk 步骤和 `./gradlew` 都失败；Git Bash 每个 runner 都有，
  而 Gradle wrapper 本身能识别 MSYS。
- **不需要 MSVC 环境预激活**。`GPL/vsconfig.gradle` 会自己用 `vswhere.exe` 找 Visual Studio，
  再从 `vcvarsall.bat` 读出 SDK 版本，所以不用引入第三方的 msvc-dev-cmd action。
  `windows-latest` 自带 VS 的 C++ 工作负载（MSVC + Windows SDK + ATL），正好满足
  `CheckToolChain` 的要求。
- **必须强制 LF 签出**（最反直觉的一个坑，踩过一次）。Ghidra 的 `gradlew` 用 POSIX 的
  `read` 循环逐行读 `application.properties`，再校验 `application.release.name` 是不是
  `PUBLIC`/`DEV`。而 `.gitattributes` 里 `*.properties text` 意味着**按平台原生换行符签出**，
  Windows 上就是 CRLF——读出来的值变成 `DEV\r`，校验必然失败，然后脚本抛出一句极具误导性的
  `Please install Gradle 8.5 or later and put it on your PATH.`（其实 Gradle 一点问题没有）。
  所以 checkout **之前**要同时设 `core.autocrlf=false` **和** `core.eol=lf`：
  只设前者不够，因为 `core.eol` 默认是 `native`；只设后者也不行，因为 `autocrlf=true` 会覆盖它。
  真正需要 CRLF 的 `.bat`/`.sln`/`.vcxproj` 在 `.gitattributes` 里带**显式** `eol=crlf`，
  优先级高于 `core.eol`，所以 MSVC 工具链不受影响。
- **长路径**。Ghidra 源码树本身就深，构建产物还要再深几层，会撞上 260 字符上限；
  同样要在 checkout **之前**设 `git config --system core.longpaths true`。
- **Python 用 `actions/setup-python`**，统一调 `python`（Git Bash 里通常没有 `python3`）。
  Gradle 自己会按 `python3 / python / py` 顺序探测，setup-python 保证版本落在
  `application.python.supported` 范围内。
- **`fail-fast: false`**：一个平台挂掉不会连累另一个，Linux 包照常产出。

## 已知边界

- `@PluginInfo` 的插件描述是 Java 注解值，必须是编译期常量，**无法**走运行时钩子，目前保持英文。
- JavaHelp 的全文索引器不做中文分词，中文帮助的“搜索”标签页效果有限（目录导航不受影响）。
- 帮助译文必须显式声明 UTF-8：上游页面多为 `charset=windows-1252`，照抄会乱码。
