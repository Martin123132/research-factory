CREATE TABLE `activity_events` (
	`sequence` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`event_id` text NOT NULL,
	`event_type` text NOT NULL CHECK (`event_type` IN ('HANGAR_WORK_ORDER_CREATED', 'HANGAR_WORK_ORDER_STATE_CHANGED', 'HANGAR_RUNNER_REGISTERED')),
	`entity_type` text NOT NULL CHECK (`entity_type` IN ('WORK_ORDER', 'RUNNER')),
	`entity_id` text NOT NULL,
	`entity_version` integer NOT NULL,
	`mode` text NOT NULL CHECK (`mode` IN ('HANGAR_CONSTRUCTION', 'SYNTHETIC_COMMISSIONING')),
	`actor_user_id` text NOT NULL,
	`actor_display` text NOT NULL,
	`summary` text NOT NULL,
	`payload_json` text DEFAULT '{}' NOT NULL,
	`scientific_evidence` integer DEFAULT false NOT NULL CHECK (`scientific_evidence` = 0),
	`counts_as_independent_reproduction` integer DEFAULT false NOT NULL CHECK (`counts_as_independent_reproduction` = 0),
	`eligible_for_promotion` integer DEFAULT false NOT NULL CHECK (`eligible_for_promotion` = 0),
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `activity_events_event_id_unique` ON `activity_events` (`event_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `activity_events_entity_version_idx` ON `activity_events` (`entity_type`,`entity_id`,`entity_version`);--> statement-breakpoint
CREATE INDEX `activity_events_type_idx` ON `activity_events` (`event_type`);--> statement-breakpoint
CREATE INDEX `activity_events_entity_idx` ON `activity_events` (`entity_type`,`entity_id`);--> statement-breakpoint
CREATE INDEX `activity_events_mode_idx` ON `activity_events` (`mode`);--> statement-breakpoint
CREATE INDEX `activity_events_created_idx` ON `activity_events` (`created_at`);--> statement-breakpoint
CREATE TABLE `runner_profiles` (
	`id` text PRIMARY KEY NOT NULL,
	`label` text NOT NULL,
	`trust_class` text NOT NULL CHECK (`trust_class` IN ('LOCAL_TRUSTED_CODE_ONLY', 'CONTAINER_COMMISSIONING_ONLY')),
	`status` text DEFAULT 'REGISTERED' NOT NULL CHECK (`status` = 'REGISTERED'),
	`notes` text DEFAULT '' NOT NULL,
	`promotion_eligible` integer DEFAULT false NOT NULL CHECK (`promotion_eligible` = 0),
	`owner_user_id` text NOT NULL,
	`owner_display` text NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE INDEX `runner_profiles_status_idx` ON `runner_profiles` (`status`);--> statement-breakpoint
CREATE INDEX `runner_profiles_owner_idx` ON `runner_profiles` (`owner_user_id`);--> statement-breakpoint
CREATE TABLE `schema_metadata` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE TABLE `work_orders` (
	`id` text PRIMARY KEY NOT NULL,
	`workbench_id` integer NOT NULL CHECK (`workbench_id` BETWEEN 1 AND 100),
	`mode` text NOT NULL CHECK (`mode` IN ('HANGAR_CONSTRUCTION', 'SYNTHETIC_COMMISSIONING')),
	`title` text NOT NULL,
	`description` text DEFAULT '' NOT NULL,
	`status` text DEFAULT 'OPEN' NOT NULL CHECK (`status` IN ('OPEN', 'CLAIMED', 'IN_PROGRESS', 'BLOCKED', 'REVIEW', 'COMPLETED')),
	`assignee_user_id` text,
	`assignee_display` text,
	`created_by_user_id` text NOT NULL,
	`created_by_display` text NOT NULL,
	`blocked_reason` text,
	`scientific_evidence` integer DEFAULT false NOT NULL CHECK (`scientific_evidence` = 0),
	`counts_as_independent_reproduction` integer DEFAULT false NOT NULL CHECK (`counts_as_independent_reproduction` = 0),
	`eligible_for_promotion` integer DEFAULT false NOT NULL CHECK (`eligible_for_promotion` = 0),
	`revision` integer DEFAULT 0 NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`completed_at` text
);
--> statement-breakpoint
CREATE INDEX `work_orders_status_idx` ON `work_orders` (`status`);--> statement-breakpoint
CREATE INDEX `work_orders_workbench_idx` ON `work_orders` (`workbench_id`);--> statement-breakpoint
CREATE INDEX `work_orders_mode_idx` ON `work_orders` (`mode`);--> statement-breakpoint
CREATE TRIGGER `activity_events_reject_update`
BEFORE UPDATE ON `activity_events`
BEGIN SELECT RAISE(ABORT, 'activity_events is append-only'); END;--> statement-breakpoint
CREATE TRIGGER `activity_events_reject_delete`
BEFORE DELETE ON `activity_events`
BEGIN SELECT RAISE(ABORT, 'activity_events is append-only'); END;--> statement-breakpoint
INSERT INTO `schema_metadata` (`key`, `value`)
VALUES ('hangar_schema_version', '1');
