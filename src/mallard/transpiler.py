
import sqlglot
import logging
logging.getLogger("sqlglot").setLevel(logging.ERROR)
import sqlglot.expressions as exp
import json
import traceback
import time

def __log_debug(hypothesis_id, message, data):
    # #region agent log
    try:
        with open("/Users/calummcguicken/Documents/github/mallard/.cursor/debug-4f7a57.log", "a") as f:
            f.write(json.dumps({
                "sessionId": "4f7a57",
                "hypothesisId": hypothesis_id,
                "location": "transpiler.py",
                "message": message,
                "data": data,
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except Exception:
        pass
    # #endregion

def _transform_ast(node):
    if isinstance(node, exp.Table):
        if "INFORMATION_SCHEMA" in node.name.upper() or (node.db and "INFORMATION_SCHEMA" in node.db.upper()):
            # When testing locally with DuckDB, replace any dynamic partition bound queries with a dummy date.
            # E.g. date_id > (SELECT MIN(...) FROM INFORMATION_SCHEMA.PARTITIONS) becomes date_id > '1970-01-01'
            curr = node
            while curr:
                if isinstance(curr, exp.Subquery):
                    curr.replace(exp.Cast(this=exp.Literal.string("1970-01-01"), to=exp.DataType.build("DATE")))
                    break
                curr = curr.parent

    try:
        # Convert EXTRACT(DATE FROM x) to CAST(x AS DATE) since DuckDB doesn't support DATE as an extract specifier
        if isinstance(node, exp.Extract):
            if node.this.name.upper() == "DATE":
                return exp.Cast(this=node.expression.transform(_transform_ast, copy=False), to=exp.DataType.build("DATE"))
                
        # BigQuery FARM_FINGERPRINT -> DuckDB hash
        if isinstance(node, exp.FarmFingerprint):
            return exp.Anonymous(this="hash", expressions=[e.transform(_transform_ast, copy=False) for e in node.expressions])
            
        if isinstance(node, exp.Anonymous) and node.name and node.name.upper() == "FARM_FINGERPRINT":
            return exp.Anonymous(this="hash", expressions=[e.transform(_transform_ast, copy=False) for e in node.expressions])
                
        # BigQuery SELECT AS STRUCT h.* -> DuckDB SELECT h
        if isinstance(node, exp.Select):
            if node.args.get("kind") == "STRUCT":
                if len(node.expressions) == 1 and isinstance(node.expressions[0], exp.Column) and isinstance(node.expressions[0].this, exp.Star):
                    table_name = node.expressions[0].args.get("table")
                    if table_name:
                        node.set("expressions", [exp.Column(this=table_name)])
                        node.args["kind"] = None
                        
        if isinstance(node, exp.ArrayLast):
            return exp.Anonymous(this="list_last", expressions=[node.this.transform(_transform_ast, copy=False)])
                        
        if isinstance(node, exp.Table):
            # Flatten table identifiers like database.schema.table -> database_schema_table
            # Drop the catalog/project ID completely to match local execution logic
            
            # Don't flatten if it's INFORMATION_SCHEMA
            if node.args.get("db") and node.args["db"].name.upper() == "INFORMATION_SCHEMA":
                return node
                
            db_val = node.args.get("db")
            this_val = node.args.get("this")
            
            # Special case for tables inside CREATE FUNCTION statements
            if getattr(node, "_is_create_function", False):
                parts = []
                if db_val: parts.append(db_val.name)
                if this_val: parts.append(this_val.name)
                if parts:
                    new_name = "_".join(parts).replace('-', '_')
                    return exp.Table(this=exp.Identifier(this=new_name, quoted=False))
                    
            if db_val and this_val:
                parts = []
                # Intentionally omitting catalog (project id)
                parts.append(db_val.name)
                parts.append(this_val.name)
                
                new_name = "_".join(parts).replace('-', '_')
                return exp.Table(this=exp.Identifier(this=new_name, quoted=False), alias=node.args.get("alias"))
                
        elif isinstance(node, exp.Create):
            # Tag the inner table so we can flatten it without getting confused by catalog
            if isinstance(node.this, exp.UserDefinedFunction):
                this_table = node.this.this
                if isinstance(this_table, exp.Table):
                    this_table._is_create_function = True
    
            if getattr(node.this, "expressions", None):
                    for expr in node.this.expressions:
                        if isinstance(expr, exp.ColumnDef):
                            expr.set("kind", None)
                            expr.args["kind"] = None
                    
    
        if isinstance(node, exp.Identifier):
            name_str = node.name
            if name_str and ("PRIVATE_UDFS" in name_str.upper() or "PUBLIC_UDFS" in name_str.upper() or "PRIVATE_SUBSCRIPTIONS" in name_str.upper()):
                parts = name_str.replace('`', '').replace('"', '').replace(':', '.').split('.')
                new_name = "_".join(parts[-2:]).replace('-', '_').replace('`', '').replace('"', '').replace(' ', '')
                new_name = new_name.lower()
                if "is_grace_period_history" in name_str.lower():
                    new_name = "private_udfs_is_grace_period_history"
                elif "subscription_stage" in name_str.lower():
                    new_name = "private_udfs_subscription_stage"
                elif "consolidate_discounts" in name_str.lower():
                    new_name = "private_udfs_consolidate_discounts"
                elif "clean_up_subscription_events" in name_str.lower():
                    new_name = "private_udfs_clean_up_subscription_events"
                elif "trial_rollover" in name_str.lower():
                    new_name = "private_udfs_trial_rollover"
                
                if "enriched_subscriptions_intermediate_transformation" in name_str:
                    new_name = "private_subscriptions_enriched_subscriptions_intermediate_transformation"
                elif "enriched_subscriptions" in name_str:
                    new_name = "private_subscriptions_enriched_subscriptions"
                elif "subscription_chain_categorisation" in name_str:
                    new_name = "private_subscriptions_subscription_chain_categorisation"
                elif "monthly_user_cohort_retention_fts_continuous" in name_str:
                    new_name = "private_subscriptions_monthly_user_cohort_retention_fts_continuous"
                elif "monthly_user_cohort_retention_fts_eop" in name_str:
                    new_name = "private_subscriptions_monthly_user_cohort_retention_fts_eop"
                elif "is_grace_period_history" in name_str.lower():
                    new_name = "private_udfs_is_grace_period_history"
                    
                node.set("this", new_name)
                node.args["quoted"] = False
    
        if isinstance(node, exp.Anonymous):
            if node.name:
                if node.name.upper() == "FARM_FINGERPRINT":
                    return exp.Anonymous(this="hash", expressions=[e.transform(_transform_ast, copy=False) for e in node.expressions])
                
                if node.name.upper() == "DATE_DIFF":
                    if len(node.expressions) == 3:
                        date_part = node.expressions[0]
                        if isinstance(date_part, exp.Literal):
                            date_part_str = date_part.name.strip("'").strip('"')
                            return exp.Anonymous(this="date_diff", expressions=[exp.Identifier(this=date_part_str, quoted=False), node.expressions[1].transform(_transform_ast, copy=False), node.expressions[2].transform(_transform_ast, copy=False)])
                        
            # Flatten fully qualified function calls to match our flattened table/macro names
            func_name = node.this.name if isinstance(node.this, exp.Identifier) else node.name
            if func_name and func_name.count('.') >= 1:
                # Split by dot, take last two parts (dataset.function), replace hyphens
                parts = func_name.replace('`', '').replace('"', '').split('.')
                new_name = "_".join(parts[-2:]).replace('-', '_')
                return exp.Anonymous(this=exp.Identifier(this=new_name, quoted=False), expressions=[e.transform(_transform_ast, copy=False) for e in node.expressions])
                
        if isinstance(node, exp.In):
            if node.args.get("unnest"):
                unnest_node = node.args["unnest"]
                if isinstance(unnest_node, exp.Unnest):
                    expr = unnest_node.expressions[0] if unnest_node.expressions else exp.Null()
                    return exp.Anonymous(
                        this="list_contains",
                        expressions=[expr, node.this]
                    )
    
        if isinstance(node, exp.Unnest):
            offset = node.args.get("offset")
            if offset and offset.name.lower() == "offset":
                node.set("offset", exp.Identifier(this="offset", quoted=True))
    
            alias = node.args.get("alias")
            
            expr = node.expressions[0] if node.expressions else None
            if expr:
                expr = expr.transform(_transform_ast, copy=False)
                is_from_or_join = isinstance(node.parent, (exp.From, exp.Join))
                
                if not is_from_or_join:
                    new_unnest = exp.Unnest(
                        expressions=[
                            expr.copy(),
                            exp.PropertyEQ(
                                this=exp.Identifier(this="recursive", quoted=False),
                                expression=exp.Boolean(this=True)
                            )
                        ]
                    )
                    if alias:
                        new_unnest.set("alias", alias.copy())
                    return new_unnest
                
                explode = exp.Explode(
                    this=expr.copy(),
                    expressions=[
                        exp.PropertyEQ(
                            this=exp.Identifier(this="recursive", quoted=False),
                            expression=exp.Boolean(this=True)
                        )
                    ]
                )
                
                inner_exprs = []
                if alias:
                    if alias.args.get("columns"):
                        col_alias = alias.args["columns"][0].name
                        inner_exprs.append(exp.alias_(explode, col_alias))
                    else:
                        inner_exprs.append(explode)
                else:
                    inner_exprs.append(explode)
                
                if offset:
                    subscripts = exp.Anonymous(
                        this="generate_subscripts",
                        expressions=[expr.copy(), exp.Literal.number(1)]
                    )
                    zero_indexed = exp.Sub(this=subscripts, expression=exp.Literal.number(1))
                    offset_name = offset.name if hasattr(offset, "name") else offset.alias
                    if not offset_name and hasattr(offset, "this"):
                        offset_name = offset.this
                    inner_exprs.append(exp.alias_(zero_indexed, offset_name))
                    
                subquery = exp.Subquery(
                    this=exp.Select(expressions=inner_exprs),
                )
                
                if alias:
                    # Use the provided alias as the table alias so `alias.*` references work correctly for struct unpacking
                    subquery_alias = alias.this.name if alias.this else (alias.args.get("columns")[0].name if alias.args.get("columns") else "t_unnest")
                    subquery.set("alias", exp.TableAlias(this=exp.Identifier(this=subquery_alias, quoted=False)))
                else:
                    pass
                    
                return exp.Lateral(
                    this=subquery
                )
    
    except Exception as e:
        __log_debug("H_ERR", "Transform exception", {"error": str(e), "traceback": traceback.format_exc()})
    return node

def _qualify_unnest_aliases(node):
    if isinstance(node, exp.Select):
        aliases = []
        for join in node.args.get("joins", []):
            if isinstance(join.this, exp.Unnest):
                alias = join.this.args.get("alias")
                if alias:
                    alias_name = alias.this.name if alias.this else (alias.args.get("columns")[0].name if alias.args.get("columns") else None)
                    if alias_name: aliases.append(alias_name)
        
        if aliases:
            for col in node.find_all(exp.Column):
                if not col.args.get("table") and col.this.name in aliases:
                    col.set("table", exp.Identifier(this=col.this.name, quoted=False))
                    
    for child in node.iter_expressions():
        _qualify_unnest_aliases(child)

def transpile_to_duckdb(sql: str) -> str:
    """
    Translates BigQuery SQL syntax to DuckDB and flattens table references.
    """
    if not sql:
        return sql
        
    try:
        # Parse BigQuery SQL
        parsed = sqlglot.parse(sql, read="bigquery")
        
        transpiled_statements = []
        for stmt in parsed:
            if not stmt:
                continue
            
            # Pre-pass to qualify unqualified column references that match UNNEST aliases
            _qualify_unnest_aliases(stmt)
            
            # Apply all AST transformations
            transformed = stmt.transform(_transform_ast)
            transformed = _post_transform_macro(transformed)
            
            # Generate DuckDB SQL
            transpiled = transformed.sql(dialect="duckdb")
            transpiled_statements.append(transpiled)
            
        return ";\n".join(transpiled_statements)
    except Exception as e:
        __log_debug("H4", "Parsing fallback triggered", {"error": str(e), "sql_start": sql[:100], "traceback": traceback.format_exc()})
        # Fallback to original SQL on parsing errors, might just work or DuckDB will error
        return sql

from sqlglot.dialects.duckdb import DuckDB

# BigQuery SELECT AS STRUCT ... -> DuckDB SELECT {'col1': col1, 'col2': col2} or a row type
# We must be careful because DuckDB row types from a table alias `SELECT t FROM table AS t` returns a struct.
old_select_transform = DuckDB.Generator.TRANSFORMS.get(exp.Select)

def _duckdb_select_struct(self, expression):
    if expression.args.get("kind") == "STRUCT":
        has_star = False
        for e in expression.expressions:
            if isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star)):
                has_star = True
                break
                
        if not has_star:
            return self.select_sql(expression)
            
        expr_clone = expression.copy()
        expr_clone.args["kind"] = None
        expr_clone.expressions.append(exp.alias_(exp.Literal.number(1), "_dummy_field_to_prevent_empty_struct"))
        
        subquery = exp.Subquery(
            this=expr_clone,
            alias=exp.TableAlias(this=exp.Identifier(this="__struct_alias", quoted=False))
        )
        
        wrapper_select = exp.Select(
            expressions=[exp.Column(this=exp.Identifier(this="__struct_alias", quoted=False))]
        ).from_(subquery)
        
        return self.select_sql(wrapper_select)
        
    if old_select_transform:
        return old_select_transform(self, expression)
    return self.select_sql(expression)

DuckDB.Generator.TRANSFORMS[exp.Select] = _duckdb_select_struct

def _post_transform_macro(node):
    return node
