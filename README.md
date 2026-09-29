# Orchard

一个纯 Python 标准库实现的命令行果园经营小游戏。

## 运行

```bash
python -m unittest -v   # 全部测试
python demo.py           # 固定种子的确定性演示（约 1 秒）
python -m orchard.cli    # 交互式命令行
```

## 命令

`plant <species>`、`chop <id>`、`water <id>`、`spray`、`harvest <id>`、
`sell <species> <amount>`、`settle`、`next`、`status`、`save [path]`、
`load <path>`、`help`、`quit`。

## 规则要点（异常路径一致性）

- 喷药按每棵存活树收费，已砍伐树不计费；余额不足时整体失败、不扣钱。
- 已砍伐树不会感染虫害，也不能浇水/收获。
- 雨天清掉所有树的浇水标记（次日需重新浇水）。
- 收获时按当前状态即时计算产量（浇水 +2；有虫且未喷药减半）。
- 仓库放不下时整笔收获被拒绝，任何果实都不会入库。
- 出售数量不足或非法时不扣果实、不加钱。
- 随机事件不会与上一天连续相同（normal/rain/pest）。
- `settle` 后当天所有动作锁定，`next` 进入新一天后恢复；每棵树每天只能收获一次。

## 存档格式

JSON（`save.json`），顶层字段：`version, coins, capacity, day, settled,
next_id, last_event, event, rng_state, warehouse{apple,pear,peach},
trees[]`。空文件、空对象、缺字段、仓库超容等非法存档一律拒绝加载。
