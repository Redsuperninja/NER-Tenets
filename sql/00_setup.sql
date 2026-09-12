-- Purpose: one-time Snowflake warehouse/database/schema setup for the NER demo.
-- Safe to rerun -- every statement is idempotent (CREATE ... IF NOT EXISTS).
-- Run: snowsql -f sql/00_setup.sql

CREATE WAREHOUSE IF NOT EXISTS NER_DEMO_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE;

CREATE DATABASE IF NOT EXISTS NER_DEMO;

USE WAREHOUSE NER_DEMO_WH;
USE DATABASE NER_DEMO;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;
