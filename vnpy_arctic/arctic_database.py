from datetime import datetime
from typing import List

from pandas import DataFrame
from arctic.arctic import Arctic, CHUNK_STORE, METADATA_STORE
from arctic.date import DateRange
from arctic.chunkstore.chunkstore import ChunkStore
from arctic.store.metadata_store import MetadataStore

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, TickData
from vnpy.trader.database import (
    BaseDatabase,
    BarOverview,
    TickOverview,
    DB_TZ,
    convert_tz
)
from vnpy.trader.setting import SETTINGS


class ArcticDatabase(BaseDatabase):
    """基于Arctic的MongoDB数据库接口"""

    def __init__(self) -> None:
        """"""
        self.host: str = SETTINGS["database.host"]
        self.database: str = SETTINGS["database.database"]
        self.username: str = SETTINGS["database.user"]
        self.password: str = SETTINGS["database.password"]

        # 初始化连接
        self.connection: Arctic = Arctic(
            self.host,
            tz_aware=True,
            tzinfo=DB_TZ,
            username=self.username,
            password=self.password
        )

        # 初始化实例
        self.connection.initialize_library(f"{self.database}.bar_data", CHUNK_STORE)
        self.connection.initialize_library(f"{self.database}.tick_data", CHUNK_STORE)
        self.connection.initialize_library(f"{self.database}.bar_overview", METADATA_STORE)
        self.connection.initialize_library(f"{self.database}.tick_overview", METADATA_STORE)

        # 获取数据库
        self.bar_library: ChunkStore = self.connection[f"{self.database}.bar_data"]
        self.tick_library: ChunkStore = self.connection[f"{self.database}.tick_data"]
        self.bar_overview_library: MetadataStore = self.connection[f"{self.database}.bar_overview"]
        self.tick_overview_library: MetadataStore = self.connection[f"{self.database}.tick_overview"]

    def save_bar_data(self, bars: List[BarData], stream: bool = True) -> bool:
        """保存K线数据"""
        # 转换数据为DataFrame
        data: list = []

        for bar in bars:
            d: dict = {
                "date": convert_tz(bar.datetime),
                "open_price": bar.open_price,
                "high_price": bar.high_price,
                "low_price": bar.low_price,
                "close_price": bar.close_price,
                "volume": bar.volume,
                "turnover": bar.turnover,
                "open_interest": bar.open_interest,
            }

            data.append(d)

        df: DataFrame = DataFrame.from_records(data)

        # 生成数据表名
        bar: BarData = bars[0]
        symbol: str = bar.symbol
        table_name: str = generate_table_name(symbol, bar.exchange, bar.interval)

        # 将数据更新到数据库中
        self.bar_library.update(
            table_name, df, upsert=True, chunk_size="M", chunk_range=DateRange(df.date.min(), df.date.max())
        )

        # 更新K线汇总数据
        info: dict = self.bar_library.get_info(table_name)
        count: int = info["len"]

        metadata: dict = self.bar_overview_library.read(table_name)

        if not metadata:
            metadata = {
                "symbol": symbol,
                "exchange": bar.exchange.value,
                "interval": bar.interval.value,
                "start": bars[0].datetime,
                "end": bars[-1].datetime,
                "count": count
            }
        elif stream:
            metadata["end"] = bars[-1].datetime
            metadata["count"] += len(bars)
        else:
            metadata["start"] = min(metadata["start"], bars[0].datetime)
            metadata["end"] = max(metadata["end"], bars[-1].datetime)
            metadata["count"] = count

        self.bar_overview_library.append(
            table_name,
            metadata,
            start_time=datetime.now(DB_TZ)
        )

        return True

    def save_tick_data(self, ticks: List[TickData], stream: bool = False) -> bool:
        """保存TICK数据"""
        # 转换数据为DataFrame
        data: list = []

        for tick in ticks:
            d: dict = {
                "date": convert_tz(tick.datetime),
                "name": tick.name,
                "volume": tick.volume,
                "turnover": tick.turnover,
                "open_interest": tick.open_interest,
                "last_price": tick.last_price,
                "last_volume": tick.last_volume,
                "limit_up": tick.limit_up,
                "limit_down": tick.limit_down,
                "open_price": tick.open_price,
                "high_price": tick.high_price,
                "low_price": tick.low_price,
                "pre_close": tick.pre_close,
                "bid_price_1": tick.bid_price_1,
                "bid_price_2": tick.bid_price_2,
                "bid_price_3": tick.bid_price_3,
                "bid_price_4": tick.bid_price_4,
                "bid_price_5": tick.bid_price_5,
                "ask_price_1": tick.ask_price_1,
                "ask_price_2": tick.ask_price_2,
                "ask_price_3": tick.ask_price_3,
                "ask_price_4": tick.ask_price_4,
                "ask_price_5": tick.ask_price_5,
                "bid_volume_1": tick.bid_volume_1,
                "bid_volume_2": tick.bid_volume_2,
                "bid_volume_3": tick.bid_volume_3,
                "bid_volume_4": tick.bid_volume_4,
                "bid_volume_5": tick.bid_volume_5,
                "ask_volume_1": tick.ask_volume_1,
                "ask_volume_2": tick.ask_volume_2,
                "ask_volume_3": tick.ask_volume_3,
                "ask_volume_4": tick.ask_volume_4,
                "ask_volume_5": tick.ask_volume_5,
                "localtime": tick.localtime,
            }
            data.append(d)

        df: DataFrame = DataFrame.from_records(data)

        # 生成数据表名
        tick: TickData = ticks[0]
        symbol: str = tick.symbol
        table_name: str = generate_table_name(symbol, tick.exchange)

        # 将数据更新到数据库中
        self.tick_library.update(
            table_name, df, upsert=True, chunk_size="M", chunk_range=DateRange(df.date.min(), df.date.max())
        )

        # 更新Tick线汇总数据
        info: dict = self.tick_library.get_info(table_name)
        count: int = info["len"]

        metadata: dict = self.tick_overview_library.read(table_name)

        if not metadata:
            metadata = {
                "symbol": symbol,
                "exchange": tick.exchange.value,
                "start": ticks[0].datetime,
                "end": ticks[-1].datetime,
                "count": count
            }
        elif stream:
            metadata["end"] = ticks[-1].datetime
            metadata["count"] += len(ticks)
        else:
            metadata["start"] = min(metadata["start"], ticks[0].datetime)
            metadata["end"] = max(metadata["end"], ticks[-1].datetime)
            metadata["count"] = count

        self.tick_overview_library.append(
            table_name,
            metadata,
            start_time=datetime.now(DB_TZ)
        )

        return True

    def load_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> List[BarData]:
        """读取K线数据"""
        table_name: str = generate_table_name(symbol, exchange, interval)
        df: DataFrame = self.bar_library.read(
            table_name, chunk_range=DateRange(start, end))

        if df.empty:
            return []

        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        df = df.tz_localize(DB_TZ)

        bars: List[BarData] = []

        for tp in df.itertuples():
            bar: BarData = BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=tp.Index.to_pydatetime(),
                interval=interval,
                volume=tp.volume,
                turnover=tp.turnover,
                open_interest=tp.open_interest,
                open_price=tp.open_price,
                high_price=tp.high_price,
                low_price=tp.low_price,
                close_price=tp.close_price,
                gateway_name="DB"
            )
            bars.append(bar)

        return bars

    def load_tick_data(
        self,
        symbol: str,
        exchange: Exchange,
        start: datetime,
        end: datetime
    ) -> List[TickData]:
        """读取Tick数据"""
        table_name: str = generate_table_name(symbol, exchange)
        df: DataFrame = self.tick_library.read(
            table_name, chunk_range=DateRange(start, end))

        if df.empty:
            return []

        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        df = df.tz_localize(DB_TZ)

        ticks: List[TickData] = []

        for tp in df.itertuples():
            tick: TickData = TickData(
                symbol=symbol,
                exchange=exchange,
                datetime=tp.Index.to_pydatetime(),
                name=tp.name,
                volume=tp.volume,
                turnover=tp.turnover,
                open_interest=tp.open_interest,
                last_price=tp.last_price,
                last_volume=tp.last_volume,
                limit_up=tp.limit_up,
                limit_down=tp.limit_down,
                open_price=tp.open_price,
                high_price=tp.high_price,
                low_price=tp.low_price,
                pre_close=tp.pre_close,
                bid_price_1=tp.bid_price_1,
                bid_price_2=tp.bid_price_2,
                bid_price_3=tp.bid_price_3,
                bid_price_4=tp.bid_price_4,
                bid_price_5=tp.bid_price_5,
                ask_price_1=tp.ask_price_1,
                ask_price_2=tp.ask_price_2,
                ask_price_3=tp.ask_price_3,
                ask_price_4=tp.ask_price_4,
                ask_price_5=tp.ask_price_5,
                bid_volume_1=tp.bid_volume_1,
                bid_volume_2=tp.bid_volume_2,
                bid_volume_3=tp.bid_volume_3,
                bid_volume_4=tp.bid_volume_4,
                bid_volume_5=tp.bid_volume_5,
                ask_volume_1=tp.ask_volume_1,
                ask_volume_2=tp.ask_volume_2,
                ask_volume_3=tp.ask_volume_3,
                ask_volume_4=tp.ask_volume_4,
                ask_volume_5=tp.ask_volume_5,
                localtime=tp.localtime,
                gateway_name="DB"
            )
            ticks.append(tick)

        return ticks

    def delete_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval
    ) -> int:
        """删除K线数据"""
        # 生成表名
        table_name: str = generate_table_name(symbol, exchange, interval)

        # 查询总数据量
        info: dict = self.bar_library.get_info(table_name)
        count: int = info["len"]

        # 删除数据
        self.bar_library.delete(table_name)

        # 删除K线汇总数据
        self.bar_overview_library.purge(table_name)

        return count

    def delete_tick_data(
        self,
        symbol: str,
        exchange: Exchange
    ) -> int:
        """删除Tick数据"""
        # 生成表名
        table_name: str = generate_table_name(symbol, exchange)

        # 查询总数据量
        info: dict = self.tick_library.get_info(table_name)
        count: int = info["len"]

        # 删除数据
        self.tick_library.delete(table_name)

        # 删除Tick线汇总数据
        self.tick_overview_library.purge(table_name)

        return count

    def get_bar_overview(self) -> List[BarOverview]:
        """"查询数据库中的K线汇总信息"""
        overviews: List[BarOverview] = []

        table_names: list = self.overview_library.list_symbols()
        for table_name in table_names:
            metadata: dict = self.overview_library.read(table_name)

            overview: BarOverview = BarOverview(
                symbol=metadata["symbol"],
                exchange=Exchange(metadata["exchange"]),
                interval=Interval(metadata["interval"]),
                start=metadata["start"],
                end=metadata["end"],
                count=metadata["count"]
            )

            overviews.append(overview)

        return overviews

    def get_tick_overview(self) -> List[TickOverview]:
        """"查询数据库中的Tick汇总信息"""
        overviews = []

        table_names = self.tick_overview_library.list_symbols()
        for table_name in table_names:
            metadata = self.tick_overview_library.read(table_name)

            overview = TickOverview(
                symbol=metadata["symbol"],
                exchange=Exchange(metadata["exchange"]),
                start=metadata["start"],
                end=metadata["end"],
                count=metadata["count"]
            )

            overviews.append(overview)

        return overviews


def generate_table_name(symbol: str, exchange: Exchange, interval: Interval = None) -> str:
    """生成数据表名"""
    if interval:
        return f"{symbol}_{exchange.value}_{interval.value}"
    else:
        return f"{symbol}_{exchange.value}"
