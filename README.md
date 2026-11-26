# 造纸湿部断纸质控

面向造纸质检的本地工作台。内置业务样例覆盖造纸湿部断纸预警、换纸种隔离与质控放行。样例采用确定性构造，适合复现实验和核查边界行为。

## 启动

```sh
docker compose up --build -d
```

打开 `http://127.0.0.1:18202/` 查看纸卷放行单。左侧六个入口可展开运行证据。调整「复验限额」，点击「重算放行」比较处置结果。结束后执行 `docker compose down --remove-orphans`。

## 独立业务模块

- 机台抄表 `machine_reel`
- 纸种换线 `grade_change`
- 湿部特征 `wet_signals`
- 断纸拟合 `breakpoint_model`
- 质检处置 `release_order`
- 班组对账 `spool_audit`

## 查看运行结果

- `GET /api/overview` 返回默认运行及其指纹。
- `POST /api/scenario` 接收 `{"capacity": 3}`。入口接受 1–100 的整数，应用样例时使用该业务额度。
- `GET /api/stages/spool_audit` 查看该环节的独立证据，支持 `?capacity=3`。

```sh
docker compose exec -T app python -m sheetgrade.delivery evaluate --capacity 3
docker compose exec -T app pytest -q
```

数据和模型约定见 [业务契约](docs/SPEC.md)。模块、例外规则与验证入口见 [业务深度](docs/DEPTH.md)。
