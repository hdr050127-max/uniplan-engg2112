# Sydney Timetable 数据提取模块

`timetable_scraper.py` 使用 Python 标准库，按指定课程代码查询 University of Sydney 公开课表，把每个班级的明确教学日期展开为逐次活动记录。它只查询输入的代码，不遍历课程目录；相同查询的原始响应缓存 24 小时，每次网络请求至少间隔 1 秒。

## 运行

```bash
python3 timetable_scraper.py ENGG2112 AMME1362 --year 2026 --session S2C
```

当前站点的 `robots.txt` 写有 `Disallow: /`。因此实时运行默认会停止。如果你有进行这些有限查询的许可，可明确加上 `--allow-robots-disallowed`：

```bash
python3 timetable_scraper.py ENGG2112 AMME1362 --year 2026 --session S2C --allow-robots-disallowed
```

重复处理已缓存的数据无需联网：

```bash
python3 timetable_scraper.py ENGG2112 AMME1362 --year 2026 --session S2C --offline
```

需要更新座位状态时，可在允许实时查询的命令中加入 `--refresh`。缓存仅保留清洗所需的课程、活动与地点字段，不保存源响应里的教职工姓名或联系方式。

可用 `--output path/to/file.csv` 指定输出。默认写入 `data/processed/timetable_meetings_<year>_<session>_<unit-codes>_<snapshot-day>.csv`，并生成同名 `_report.json`。报告包含每门课的行数、缺失或失败状态以及验证警告。任一课程没有干净记录时，命令返回非零状态码。

## CSV 规则

- 每行是某个 `option_id` 在一个具体 `date` 的一次活动。`activitiesDays` 是日期来源，不根据星期推测整学期每周上课。
- `group_id = subject_offering|activity_group`；`option_id` 保留源站的 `subject_offering|activity_group|class_code`。相同选项的多个日期保持同一个 `option_id`。
- `start_min`、`end_min` 为悉尼当地时间从午夜起算的分钟；日期为 `YYYY-MM-DD`。无法解析的时间、日期或标识符不写入 CSV，并记录在报告中。
- `status` 统一为 `available`、`full`、`unknown`；`status_raw` 保留原值。`available_seats` 空白表示未知，不能当作零。
- 地点优先使用网站提供的按日期地点信息。只有所有地点都属于同一建筑时才填写 `building_code`，其余情况留空，同时保存 `location_raw`。
- `snapshot_time` 和 `source_url` 记录数据来源。座位与课程安排可能变化，输出并不保证可成功选班。

公开课表页面使用的查询接口不是已发布的稳定 API。`--year` 和 `--session` 仅筛选当前网站返回的数据，不能切换网站自身发布的年份。课表活动组也不能单独证明某组是必修；后续生成候选课表前，应另行核实课程要求。
