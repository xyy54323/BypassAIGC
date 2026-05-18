from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """数据库会话依赖"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库 - 安全地创建或更新数据库结构"""
    try:
        from app.models import models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        _migrate_database_schema()
        _add_performance_indexes()

        print("[OK] 数据库初始化成功")
        return True
    except Exception as e:
        print(f"[ERROR] 数据库初始化失败: {str(e)}")
        raise


def _add_column_safely(conn, table_name, column_name, column_def):
    """安全地添加列（如果不存在）"""
    try:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False


def _add_performance_indexes():
    """添加性能优化索引"""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        indexes = [
            ("idx_opt_session_user_id", "optimization_sessions", "user_id"),
            ("idx_opt_session_status", "optimization_sessions", "status"),
            ("idx_opt_session_created_at", "optimization_sessions", "created_at"),
            ("idx_opt_segment_session_id", "optimization_segments", "session_id"),
            ("idx_opt_segment_index", "optimization_segments", "segment_index"),
            ("idx_opt_segment_status", "optimization_segments", "status"),
            ("idx_change_log_session_id", "change_logs", "session_id"),
            ("idx_change_log_segment_index", "change_logs", "segment_index"),
            ("idx_change_log_stage", "change_logs", "stage"),
        ]

        with engine.connect() as conn:
            for index_name, table_name, column_name in indexes:
                if table_name not in tables:
                    continue

                try:
                    existing_indexes = inspector.get_indexes(table_name)
                    index_names = {idx['name'] for idx in existing_indexes}
                    if index_name in index_names:
                        continue

                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_name})"
                    ))
                    conn.commit()
                    print(f"  [OK] 添加索引: {index_name}")
                except Exception:
                    conn.rollback()
                    pass

    except Exception as e:
        print(f"  [WARN] 添加性能索引警告: {str(e)}")


def _migrate_database_schema():
    """迁移数据库结构 - 添加新列到已存在的表"""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        with engine.connect() as conn:
            if "optimization_sessions" in tables:
                columns = {column["name"] for column in inspector.get_columns("optimization_sessions")}

                if "failed_segment_index" not in columns:
                    if _add_column_safely(conn, "optimization_sessions", "failed_segment_index", "INTEGER"):
                        print("  [OK] 添加字段: optimization_sessions.failed_segment_index")

                if "processing_mode" not in columns:
                    if _add_column_safely(conn, "optimization_sessions", "processing_mode", "VARCHAR(50) DEFAULT 'paper_polish_enhance'"):
                        print("  [OK] 添加字段: optimization_sessions.processing_mode")

                if "source_doc_token" not in columns:
                    if _add_column_safely(conn, "optimization_sessions", "source_doc_token", "VARCHAR(255)"):
                        print("  [OK] 添加字段: optimization_sessions.source_doc_token")

                if "source_doc_filename" not in columns:
                    if _add_column_safely(conn, "optimization_sessions", "source_doc_filename", "VARCHAR(255)"):
                        print("  [OK] 添加字段: optimization_sessions.source_doc_filename")

            if "users" in tables:
                user_columns = {column["name"] for column in inspector.get_columns("users")}

                if "usage_limit" not in user_columns:
                    if _add_column_safely(conn, "users", "usage_limit", f"INTEGER DEFAULT {settings.DEFAULT_USAGE_LIMIT}"):
                        print("  [OK] 添加字段: users.usage_limit")

                if "usage_count" not in user_columns:
                    if _add_column_safely(conn, "users", "usage_count", "INTEGER DEFAULT 0"):
                        print("  [OK] 添加字段: users.usage_count")

                try:
                    conn.execute(text(f"UPDATE users SET usage_limit = {settings.DEFAULT_USAGE_LIMIT} WHERE usage_limit IS NULL"))
                    conn.execute(text("UPDATE users SET usage_count = 0 WHERE usage_count IS NULL"))
                    conn.commit()
                except Exception:
                    conn.rollback()

            if "optimization_segments" in tables:
                segment_columns = {column["name"] for column in inspector.get_columns("optimization_segments")}

                if "is_title" not in segment_columns:
                    if _add_column_safely(conn, "optimization_segments", "is_title", "BOOLEAN DEFAULT 0"):
                        print("  [OK] 添加字段: optimization_segments.is_title")

                if "source_doc_paragraph_index" not in segment_columns:
                    if _add_column_safely(conn, "optimization_segments", "source_doc_paragraph_index", "INTEGER"):
                        print("  [OK] 添加字段: optimization_segments.source_doc_paragraph_index")

            if "custom_prompts" in tables:
                prompt_columns = {column["name"] for column in inspector.get_columns("custom_prompts")}

                if "is_system" not in prompt_columns:
                    if _add_column_safely(conn, "custom_prompts", "is_system", "BOOLEAN DEFAULT 0"):
                        print("  [OK] 添加字段: custom_prompts.is_system")

                if "is_active" not in prompt_columns:
                    if _add_column_safely(conn, "custom_prompts", "is_active", "BOOLEAN DEFAULT 1"):
                        print("  [OK] 添加字段: custom_prompts.is_active")

    except Exception as e:
        print(f"  [WARN] 数据库迁移警告: {str(e)}")
