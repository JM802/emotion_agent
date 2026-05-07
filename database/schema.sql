-- emotion_agent 数据库建表脚本
-- 用法: mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS emotion_agent
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE emotion_agent;

-- 原始文本表
CREATE TABLE IF NOT EXISTS raw_text (
    id          VARCHAR(64) NOT NULL COMMENT '消息ID',
    user_id     VARCHAR(64) NOT NULL COMMENT '用户ID',
    text        TEXT        NOT NULL COMMENT '文本内容',
    source      VARCHAR(32) NOT NULL COMMENT '来源（chat/comment/review等）',
    created_at  DATETIME    NOT NULL COMMENT '原始时间戳',
    PRIMARY KEY (id),
    INDEX idx_user_id (user_id),
    INDEX idx_source (source),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='原始文本表';

-- 分析结果表
CREATE TABLE IF NOT EXISTS emotion_result (
    id                  BIGINT       NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    text_id             VARCHAR(64)  NOT NULL COMMENT '关联raw_text的ID',
    sample_type         VARCHAR(32)  NOT NULL COMMENT '样本类型（direct/sarcasm_suspected/mix）',
    emotion             VARCHAR(16)  NOT NULL COMMENT '最终情绪标签',
    secondary_emotion   VARCHAR(16)  NULL     COMMENT '次情绪（mix类型时使用）',
    intensity           INT          NOT NULL COMMENT '情绪强度（0-100）',
    final_confidence    DECIMAL(4,2) NOT NULL COMMENT '最终置信度',
    is_sarcasm          TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否反讽',
    is_mixed            TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否混合情绪',
    reason              TEXT         NULL     COMMENT '判断理由',
    tokens              JSON         NULL     COMMENT '分词结果',
    emotion_words       JSON         NULL     COMMENT '情绪词列表',
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '分析时间',
    PRIMARY KEY (id),
    FOREIGN KEY (text_id) REFERENCES raw_text(id),
    INDEX idx_text_id (text_id),
    INDEX idx_emotion (emotion),
    INDEX idx_sample_type (sample_type),
    INDEX idx_is_sarcasm (is_sarcasm),
    INDEX idx_is_mixed (is_mixed),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='情绪分析结果表';
