import itertools
import json
from datetime import datetime
from typing import Any, Tuple

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, create_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from tqdm import tqdm

Base = declarative_base()


def grouper(iterable, n, fillvalue=None):
    """Collect data into fixed-length chunks or blocks"""
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    # https://docs.python.org/3/library/itertools.html#itertools-recipes
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


# noinspection SpellCheckingInspection
class Connect:
    engine = create_engine(f'postgresql+psycopg2://vkinder:12345@localhost:5432/vkinder')
    Session = sessionmaker(bind=engine)
    session = Session()

    def _insert_basics(self) -> None:
        """ Метод для записи в БД первичных данных из файлов.
        Если файлов с топонимами нет, то нужно запустить из VK_SCOPE/vk_scope методы _get_countries,
        _get_regions, _get_citiesсбор данных займёт минимум 1 час"""

        files = [
            "../DB/Fixtures/primary_data.json",
            "../DB/Fixtures/countries.json",
            "../DB/Fixtures/regions.json",
            "../DB/Fixtures/cities.json"
        ]

        table_to_model_mapping = {
            "sex": Sex,
            "status": Status,
            "sort": Sort,
            "country": Country,
            "city": City,
            "region": Region
        }

        # дополняем некоторые объекты вот этими данными
        additional_fields = {
            "city": {"area": None, "region": None, "important": None}
        }

        for file in files:
            with open(file, encoding='utf-8') as f:
                data = json.load(f)

            # извлекаем объекты группами, так чтобы в одну группу попадали
            # объекты одной и той же модели
            by_model = lambda d: d['model']
            for k, group in itertools.groupby(data, by_model):
                group = list(group)

                Model = table_to_model_mapping[k]
                table = Model.__table__

                # будем вставлять данные пачками
                for chunk in grouper(tqdm(group, desc=f"Inserting {k}..."), 1000):
                    # grouper будет добавлять в "хвост" None, обрежем их
                    chunk = [item for item in chunk if item]

                    # код дальше частично взят отсюда:
                    # https://stackoverflow.com/a/51567630/10650942

                    # через ORM невозможно сделать логику ON COFLICT DO UPDATE,
                    # поэтому придётся писать запрос на SQLAlchemy Core
                    stmt = postgresql.insert(table)

                    # конфликт по каким столбцам нас интересует -- первичный ключ
                    primary_keys = [key.name for key in inspect(table).primary_key]

                    # что обновлять при конфликте -- всё, кроме первичного ключа
                    update_dict = {c.name: c for c in stmt.excluded if
                                   not c.primary_key}

                    stmt = stmt.on_conflict_do_update(index_elements=primary_keys,
                                                      set_=update_dict)

                    # в некоторых словарях может не хватать ключей, дополним
                    rows = [{**additional_fields.get(k, {}), **ent['fields']} for ent in chunk]

                    # вжух
                    self.session.execute(stmt, rows)
                    self.session.commit()

    def insert_to_db(self, model, fields) -> None:
        """Общий метод для записи в БД новых данных"""
        entity = model(**fields)
        self.session.add(entity)
        self.session.commit()

    def select_from_db(self, model_fields, expression=None, join=None) -> Tuple[Any] or None:
        """Метод проверки наличия записей в БД"""
        if not isinstance(model_fields, tuple):
            model_fields = (model_fields,)
        if not isinstance(expression, tuple):
            expression = (expression,)
        if join:
            if not isinstance(join, tuple):
                join = (join,)
            return self.session.query(*model_fields).join(*join).filter(*expression)
        return self.session.query(*model_fields).filter(*expression)

    def update_data(self, model_fields, expression, fields) -> None:
        if not isinstance(model_fields, tuple):
            model_fields = (model_fields,)
        if not isinstance(expression, tuple):
            expression = (expression,)
        self.session.query(*model_fields).filter(*expression).update(fields)
        self.session.commit()

    def delete_from_db(self, model_fields, expression=None, join=None) -> None:
        """Общий метод для удаления данных из БД
        @rtype: object
        """
        if not isinstance(model_fields, tuple):
            model_fields = (model_fields,)
        if not isinstance(expression, tuple):
            expression = (expression,)
        self.select_from_db(*model_fields, *expression, join).delete()
        self.session.commit()


# id из Вконтакте являются натуральными Primary key для любой таблицы, описывающей соответствующую сущность
# таблица всех стран
class Country(Base):
    __tablename__ = 'country'
    id = Column(Integer, primary_key=True)
    title = Column(String)


# таблица всех регионов
class Region(Base):
    __tablename__ = 'region'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    country_id = Column(Integer, ForeignKey('country.id'))


# таблица всех городов
class City(Base):
    __tablename__ = 'city'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    important = Column(Integer, default=0)
    area = Column(String, default=None)
    region = Column(String)
    region_id = Column(Integer, ForeignKey('region.id'))


# таблица полов (бесполые/ж/м)
class Sex(Base):
    __tablename__ = 'sex'
    id = Column(Integer, primary_key=True)
    title = Column(String)


# таблица всех вариантов семейного положения ВК
class Status(Base):
    __tablename__ = 'status'
    id = Column(Integer, primary_key=True)
    title = Column(String)


# таблица вариантов сортировки поиска (по популярности/по дате регистрации)
class Sort(Base):
    __tablename__ = 'sort'
    id = Column(Integer, primary_key=True)
    title = Column(String)


# таблица, хранящая информацию о юзере
class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    date_of_birth = Column(String)
    city_id = Column(Integer, ForeignKey('city.id'))
    sex_id = Column(Integer, ForeignKey('sex.id'))
    link = Column(String)


# таблица, хранящая условия и дату поиска юзера
class Query(Base):
    __tablename__ = 'query'
    id = Column(Integer, primary_key=True, autoincrement=True)
    datetime = Column(DateTime)
    sex_id = Column(Integer, ForeignKey('sex.id'))
    city_id = Column(Integer, ForeignKey('city.id'))
    age_from = Column(Integer)
    age_to = Column(Integer)
    status_id = Column(Integer, ForeignKey('status.id'))
    sort_id = Column(Integer, ForeignKey('sort.id'))
    user_id = Column(Integer, ForeignKey('user.id'))


# таблица, хранящая информацию о результатах поиска
# noinspection SpellCheckingInspection
class DatingUser(Base):
    __tablename__ = 'datinguser'
    id = Column(Integer, primary_key=True, autoincrement=True)
    vk_id = Column(Integer)
    first_name = Column(String)
    last_name = Column(String)
    city_id = Column(Integer)
    city_title = Column(String)
    link = Column(String)
    verified = Column(Integer)
    query_id = Column(Integer, ForeignKey('query.id'))
    viewed = Column(Boolean, default=False)
    black_list = Column(Boolean, nullable=True)


if __name__ == '__main__':
    now = datetime.now()
    Base.metadata.create_all(Connect.engine)
    print("All tables are created successfully")
    # Connect()._insert_basics()
    # print("Primary inserts done")
    # print(datetime.now() - now)
