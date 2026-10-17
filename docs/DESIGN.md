# UniPlan 网站设计规格（2026-10-17，总控）

用户要求：成品网站，**简约、英文、没有 AI 味**。之前说过：不要圆角矩形，一定要简洁。
本规格只定方向和规矩，实现由系统集成窗口完成。判断规则（解析、排课、打分、理由核对的逻辑）一律不改；只改界面和显示文字。

## 1. 题材、用户、主要任务

- **题材**：悉尼大学学生排下学期的课表。最典型的东西是"一周的课表格子"，和学生自己写的那句处境。
- **用户**：本科生，多数在手机上用，一边看 Canvas 一边排课；还有看我们报告的老师。
- **主要任务**：选课 → 用一句话说处境 → 看系统怎么理解、回答一两个问题 → 拿到 3 份不冲突的课表和理由 → 挑一份、导出日历。

## 2. 记忆点（只在这一处用力）

**"你的话，被读回来了"。** 学生写的那句话用大字号留在页面上。读完后，每个被理解的短句下面画一条蓝花楹色的细下划线，右边（手机上是下方）用小一号字写出读出来的条件，像老师写在作业边上的批注。反问也写成批注："Can't, or would rather not?"，后面跟两个文字选项。读不懂的短句画灰色虚线，批注写 "Not something a timetable can use"。

其余一切保持安静。

## 3. 颜色（亮色，白底；暗色另配一套同名变量）

| 名字 | 值 | 用途 |
| --- | --- | --- |
| paper | `#FFFFFF` | 背景（不用奶油色） |
| ink | `#22283A` | 正文、主按钮底色（墨蓝，不是 #111 这类近黑） |
| muted | `#646A7B` | 次要文字、批注里的原话引用 |
| rule | `#E2E4EA` | 极少量的分隔线、输入框底线 |
| jacaranda | `#5B4E9E` | 唯一的强调色：下划线、选中的选项、焦点框、"排第 1" 的标记。不做渐变、不做大面积底色 |
| amber | `#8A5300` | 提醒文字（简化模式、排不出课表），只用文字颜色，不加底色块 |

课表格子里各门课的底色（很淡，左边一条 3px 深一点的同色边）取自悉尼的材料，按顺序分配：
sandstone `#EFE4CF`/`#B08A4E`、eucalypt `#DCE8DF`/`#5E8A6B`、harbour `#DCE6F2`/`#4F739C`、jacaranda `#E6E2F4`/`#5B4E9E`、brick `#F3DFD9`/`#A8574A`。线上课用同色的斜线纹或只有边框、不填色。

对比度都要过 WCAG AA。

## 4. 字体

- 只用一个家族：**Atkinson Hyperlegible Next**（Braille Institute 为低视力读者设计，SIL OFL 1.1，Google Fonts 有）。辨识度高，又不是 Inter / 系统字体那种默认选择，适合一个所有学生都要用的工具。
- 用 Google Fonts 的 `<link>` 加载；连不上时退回 `system-ui`，页面照样能用。
- 字号（px）：12.5 / 14 / 16（正文）/ 20 / 28（那句话的输入和回显）/ 36（结果页标题，只出现一次）。
- 行高：正文 1.5，那句话 1.35。行宽不超过 72 个字符。
- 时间、天数、小时等数字用 `font-variant-numeric: tabular-nums`。
- 字重只用 400 和 600。不用斜体强调单个词，也不给标题里单个词换颜色。

## 5. 版式

整体左对齐，单栏为主，最大宽度：输入页 720px，结果页 1120px。

```
UniPlan                                              Semester 2, 2026  ▾

Units
ENGG2112 Multidisciplinary Engineering  ×    AMME2301 Mechanics of Solids  ×
+ Add a unit

Your week, in a sentence
I work Tuesday and Thursday nights, no more than 5 hours of
class a day, and mornings aren't great.
─────────────────────────────────────────────────────────────
                                                    Read sentence

I work Tuesday and Thursday nights        Not available Tue and Thu after 6 pm
═══════════════════════════════
no more than 5 hours of class a day       At most 5 hours of class a day
═══════════════════════════════════
mornings aren't great                     Fewer early classes, if possible
══════════════════                        Can't, or would rather not?
                                          Can't    Would rather not

Lunch break?          No    30 min between 11:30 and 2 pm
Most days on campus?  No limit   2   3   4

More settings

Find timetables                       (主按钮：ink 底白字，直角)
```

结果页（桌面两栏，手机上下叠放）：

```
3 timetables, from 56 that fit

1  Mon, Tue, Wed                     Week 10, 12 to 18 October    Previous  Next
   2 days on campus                  ┌ Mon ┬ Tue ┬ Wed ┬ Thu ┬ Fri ┐
   7 h 36 min waiting a week         │     │     │     │     │     │
   First because it has one day      │  课表格子，各门课用材料色      │
   fewer on campus than option 2;    │                              │
   it has 1 h 12 min more waiting.   └──────────────────────────────┘
                                     Use this timetable   Download calendar (.ics)   Share link
2  Mon, Tue, Thu
   ...
3  ...
```

- 1 / 2 / 3 的编号保留：它们本来就是排名。
- 选中的那份左边一条 3px 的 jacaranda 竖线，不用卡片、不用阴影、不用圆角（border-radius: 0）。
- 选项按钮是文字加下划线：选中的用 jacaranda 实线下划线，没选中的没有下划线、颜色是 muted。
- 输入框只有一条底线，没有框。
- 手机宽 375px 时不能出现横向滚动；课表格子在自己的容器里横向滚动。

## 6. 动效

只有一处：读完句子时，下划线从左到右依次画出（每条 150ms，间隔 60ms），让学生看到哪些话被读懂了。`prefers-reduced-motion` 时直接显示。别的地方不做入场动画，也不做悬停动画。

## 7. 文案规矩（英文）

- 全站英文，sentence case，口语、直接。不写 AI、smart、magic、powered by；不用 emoji、感叹号、破折号；不用 "·" 串信息；按钮文字后面不加 "→"。
- 不用聊天机器人口吻：不写 "I understood…" 或 "Let me…"，写成标签和陈述："Read as"，"Not available Tue and Thu after 6 pm"。
- 按钮说清楚点了会发生什么，前后叫法一致：Read sentence、Find timetables、Use this timetable、Download calendar (.ics)。
- 出错时说清楚出了什么问题、怎么改，不道歉：
  - "No timetable fits all of these. Try one change: allow Fridays, or start at 9 instead of 9:30."
  - 简化模式："The sentence reader is offline, so a simpler one was used. Check each line below."
- 单位写全：days、h、min，时间用 "6 pm"、"9:30 am"，日期按澳洲写法 "Mon 12 October"。
- 页脚一行如实说明：
  > Timetables are built and checked by a scheduler; the sentence is read by a fine-tuned language model running on our own machine. Synthetic test data only; this is a student project for ENGG2112.

  不写营销语。

## 8. 质量底线

- 键盘能走完全流程，焦点框是 2px jacaranda 实线、偏移 2px。
- 选项组用 radio 语义（`role="radiogroup"`），批注和对应的短句用 `aria-describedby` 关联。
- 暗色模式：paper `#14161D`，ink `#E7E8EE`，muted `#9BA1B2`，rule `#2A2E3A`，jacaranda `#A99BEA`，amber `#E0A85A`；课程色降低明度。
- 完成后用 web-design-guidelines skill 审一遍，只修真问题。

## 9. 不改的东西

解析的标签和取值、反问的触发规则、排课、打分模型、理由的核对规则都不改，只改显示语言和界面。理由改成英文以后，核对规则要换成英文的同一套检查，并在 v1、v2、期末考卷上重跑一次理由评估，报告里写明这是英文版。

## 10. 第二版（2026-10-17，用户试用后提出）

### 10.1 排不出时给最接近的课表
- 不再出现"排不出课表"这种死路。先在全部要求下排；排不出来时，自动找"违反学生限制最少"的不冲突课表：
  - 先比违反了几条限制；
  - 再比违反了多少：落在不能上课时段里的分钟数、超出的天数或分钟数、哪天没留出午饭；
  - 最后用打分模型排序。
- 每份推荐的第一行写清楚违反了什么，例如 "Breaks one limit: 1 class on Wed before 9:30 am"。
- 真正的课程冲突（同一时间两节必须去的课）永远不允许。如果课程本身就排不开，就从有录播的讲座里挑一节改成看录播，选缺课时长最少的，写明 "Watch the recording of AMME2301 Lecture 2"。还是不行，才说明哪两门课冲突。
- 这是排不出来时才走的后备路径，排得出时什么都不变。打分模型、解析、期末考试的成绩都不受影响。

### 10.2 按钮看得见，文字少
- 主按钮：ink 实心底、白字、直角，高 44px。次要按钮：1px ink 边框、直角、透明底。选项组：相连的直角方块，选中的格子用 jacaranda 填满、字是白色，没选中的是细边框。可点的东西高度至少 40px。仍然不用圆角卡片和阴影。
- 文字预算：每块只留必要的一句。删掉：
  - 操作说明（Enter、方向键、Compare 用法、Select a day…）；
  - 结果统计（from N that fit、N candidates ranked、N ways to get this same week、Just as good on…）；
  - 数据日期（移到页脚）；
  - "These are filled in below…" 这类过渡句。
  需要读屏时，放进 visually-hidden 或 aria 属性里。
- 推荐理由压成一行："Fewest one-class days. Costs 2 h 32 min more waiting." 天数和课表已经在标题和周视图里，理由里不再重复。
- 每个短句后面的 "Leave this out" 改成小的 × 按钮，aria-label 写 "Leave this out"。
- 结果页默认只露出：
  - 3 份推荐（标题、三个数字、一行理由）；
  - 周视图；
  - Use this timetable 和 Download calendar。
  Share、Save、Print、学期视图、Hours、Enrolment、With a friend、研究保存收进一个 "More" 里。
- "Loosening one limit would help…" 只在推荐违反了限制、或用户自己展开时才显示。
