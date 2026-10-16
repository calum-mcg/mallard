from google.cloud import bigquery
import sqlglot

client = bigquery.Client()

def get_underlying_tables(view_query):
    try:
        parsed = sqlglot.parse_one(view_query, read='bigquery')
        return [table.sql(dialect='bigquery') for table in parsed.find_all(sqlglot.exp.Table)]
    except Exception as e:
        print(f'Sqlglot error: {e}')
        return []

view = client.get_table('sc-corpus.views_entity_attributes.user')
tables = get_underlying_tables(view.view_query)
print(f'Underlying tables: {tables}')

for t in tables:
    t_clean = t.replace('`', '')
    try:
        underlying = client.get_table(t_clean)
        print(f'{t_clean} type: {underlying.table_type}')
        if underlying.table_type == 'TABLE' and underlying.time_partitioning:
            print(f'  Partition field: {underlying.time_partitioning.field}')
        elif underlying.table_type == 'VIEW':
            print(f'  View query: {underlying.view_query}')
            sub_tables = get_underlying_tables(underlying.view_query)
            print(f'  Sub-tables: {sub_tables}')
            for sub_t in sub_tables:
                sub_t_clean = sub_t.replace('`', '')
                try:
                    sub_underlying = client.get_table(sub_t_clean)
                    if sub_underlying.table_type == 'TABLE' and sub_underlying.time_partitioning:
                        print(f'    Sub-partition field: {sub_underlying.time_partitioning.field}')
                except Exception:
                    pass
    except Exception as e:
        print(f'Error getting {t_clean}: {e}')
