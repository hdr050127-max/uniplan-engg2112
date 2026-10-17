# 校园建筑位置

`data/locations/buildings.json` 是本地建筑位置索引。当前收录现有课表快照使用的 19 个建筑代码。坐标来自[悉尼大学校园地图](https://maps.sydney.edu.au/)所使用的 MazeMap 建筑搜索结果；每条记录必须有唯一、完全一致的建筑代码才会写入。`latitude` / `longitude` 是地图中的**建筑点**，不能当作教室、楼层、入口或步行路线位置。

更新课表快照后运行：

```bash
python3 sync_building_locations.py
```

脚本只查询尚未缓存的建筑代码，逐次请求至少间隔一秒。需要重新核对已有位置时用 `--refresh`；也可用 `--code J07` 单独添加建筑。运行中的本地服务需要重启，才能读到更新后的缓存。

课表 API 的 `building_location` 包含建筑名、经纬度、官方地图链接及精度。未知代码仍可打开官方地图进行人工核对，但经纬度为 `null`，`precision` 为 `unverified`。没有建筑代码或线上活动不附加建筑位置。原始教室描述保留在 `location_raw`；排课的换楼缓冲仍是学生输入的分钟数，不会把建筑点之间的直线距离当作步行时间。
