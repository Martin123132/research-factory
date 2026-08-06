CREATE TABLE IF NOT EXISTS `shift_reports` (
	`sequence` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`report_id` text NOT NULL,
	`work_order_id` text NOT NULL,
	`report_sequence` integer NOT NULL,
	`previous_report_sha256` text,
	`report_sha256` text NOT NULL,
	`workbench_id` integer NOT NULL,
	`mode` text NOT NULL,
	`work_order_revision` integer NOT NULL,
	`work_order_status` text NOT NULL,
	`outcome_class` text NOT NULL,
	`report_json` text NOT NULL,
	`actor_user_id` text NOT NULL,
	`actor_display` text NOT NULL,
	`scientific_evidence` integer DEFAULT false NOT NULL,
	`counts_as_independent_reproduction` integer DEFAULT false NOT NULL,
	`eligible_for_promotion` integer DEFAULT false NOT NULL,
	`closes_work_order` integer DEFAULT false NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`work_order_id`) REFERENCES `work_orders`(`id`) ON UPDATE no action ON DELETE restrict,
	CONSTRAINT "shift_reports_sequence_check" CHECK("shift_reports"."report_sequence" >= 1),
	CONSTRAINT "shift_reports_workbench_check" CHECK("shift_reports"."workbench_id" BETWEEN 1 AND 100),
	CONSTRAINT "shift_reports_mode_check" CHECK("shift_reports"."mode" IN ('HANGAR_CONSTRUCTION', 'SYNTHETIC_COMMISSIONING')),
	CONSTRAINT "shift_reports_status_check" CHECK("shift_reports"."work_order_status" IN ('CLAIMED', 'IN_PROGRESS', 'BLOCKED')),
	CONSTRAINT "shift_reports_outcome_check" CHECK("shift_reports"."outcome_class" IN ('PROGRESS', 'NO_GAIN', 'BLOCKED', 'UNRUNNABLE')),
	CONSTRAINT "shift_reports_chain_check" CHECK((("shift_reports"."report_sequence" = 1 AND "shift_reports"."previous_report_sha256" IS NULL) OR ("shift_reports"."report_sequence" > 1 AND "shift_reports"."previous_report_sha256" IS NOT NULL))),
	CONSTRAINT "shift_reports_no_evidence_check" CHECK("shift_reports"."scientific_evidence" = 0),
	CONSTRAINT "shift_reports_no_reproduction_check" CHECK("shift_reports"."counts_as_independent_reproduction" = 0),
	CONSTRAINT "shift_reports_no_promotion_check" CHECK("shift_reports"."eligible_for_promotion" = 0),
	CONSTRAINT "shift_reports_no_completion_check" CHECK("shift_reports"."closes_work_order" = 0)
);
--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `shift_reports_report_id_unique` ON `shift_reports` (`report_id`);--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `shift_reports_report_sha256_unique` ON `shift_reports` (`report_sha256`);--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `shift_reports_work_order_sequence_idx` ON `shift_reports` (`work_order_id`,`report_sequence`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `shift_reports_work_order_idx` ON `shift_reports` (`work_order_id`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `shift_reports_outcome_idx` ON `shift_reports` (`outcome_class`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `shift_reports_created_idx` ON `shift_reports` (`created_at`);--> statement-breakpoint
INSERT INTO `schema_metadata` (`key`, `value`, `updated_at`)
VALUES ('hangar_schema_version', '2', CURRENT_TIMESTAMP)
ON CONFLICT(`key`) DO UPDATE SET `value` = excluded.`value`, `updated_at` = CURRENT_TIMESTAMP;
