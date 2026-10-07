-- MySQL dump 10.13  Distrib 8.4.3, for Win64 (x86_64)
--
-- Host: localhost    Database: fbr_invoice_uploader
-- ------------------------------------------------------
-- Server version	8.4.3

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `report_templates`
--

DROP TABLE IF EXISTS `report_templates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `report_templates` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(120) NOT NULL,
  `description` varchar(500) DEFAULT NULL,
  `definition` json NOT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_by_user_id` int DEFAULT NULL,
  `created_by_role` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `ix_report_templates_updated_at` (`updated_at`),
  KEY `ix_report_templates_id` (`id`),
  KEY `ix_report_templates_created_at` (`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `report_templates`
--

LOCK TABLES `report_templates` WRITE;
/*!40000 ALTER TABLE `report_templates` DISABLE KEYS */;
INSERT INTO `report_templates` VALUES (1,'Default Dashboard','Default reporting dashboard','{\"version\": 1, \"widgets\": [{\"type\": \"kpi\", \"title\": \"Total Invoices\", \"metric\": \"total_invoices\"}, {\"type\": \"kpi\", \"title\": \"Total Amount\", \"metric\": \"total_amount\"}, {\"type\": \"kpi\", \"title\": \"Avg Invoice\", \"metric\": \"avg_invoice_amount\"}, {\"type\": \"chart\", \"title\": \"Daily Sales\", \"metric\": \"daily_sales\"}, {\"type\": \"chart\", \"title\": \"Status Breakdown\", \"metric\": \"status_breakdown\"}, {\"type\": \"table\", \"title\": \"Invoices\", \"metric\": \"invoices\"}]}',1,NULL,'admin','2026-04-11 04:10:54','2026-04-11 04:10:54');
/*!40000 ALTER TABLE `report_templates` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `report_schedules`
--

DROP TABLE IF EXISTS `report_schedules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `report_schedules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `template_id` int NOT NULL,
  `enabled` tinyint(1) DEFAULT NULL,
  `interval_minutes` int DEFAULT NULL,
  `export_format` varchar(10) DEFAULT NULL,
  `recipients` json DEFAULT NULL,
  `last_run_at` datetime DEFAULT NULL,
  `created_by_user_id` int DEFAULT NULL,
  `created_by_role` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_report_schedules_last_run_at` (`last_run_at`),
  KEY `ix_report_schedules_enabled` (`enabled`),
  KEY `ix_report_schedules_id` (`id`),
  KEY `ix_report_schedules_template_id` (`template_id`),
  KEY `ix_report_schedules_updated_at` (`updated_at`),
  KEY `ix_report_schedules_created_at` (`created_at`),
  CONSTRAINT `report_schedules_ibfk_1` FOREIGN KEY (`template_id`) REFERENCES `report_templates` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `report_schedules`
--

LOCK TABLES `report_schedules` WRITE;
/*!40000 ALTER TABLE `report_schedules` DISABLE KEYS */;
/*!40000 ALTER TABLE `report_schedules` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `report_runs`
--

DROP TABLE IF EXISTS `report_runs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `report_runs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `schedule_id` int NOT NULL,
  `status` varchar(20) DEFAULT NULL,
  `started_at` datetime DEFAULT NULL,
  `finished_at` datetime DEFAULT NULL,
  `file_path` varchar(500) DEFAULT NULL,
  `error_message` varchar(1000) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_report_runs_schedule_id` (`schedule_id`),
  KEY `ix_report_runs_finished_at` (`finished_at`),
  KEY `ix_report_runs_id` (`id`),
  KEY `ix_report_runs_started_at` (`started_at`),
  KEY `ix_report_runs_status` (`status`),
  CONSTRAINT `report_runs_ibfk_1` FOREIGN KEY (`schedule_id`) REFERENCES `report_schedules` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `report_runs`
--

LOCK TABLES `report_runs` WRITE;
/*!40000 ALTER TABLE `report_runs` DISABLE KEYS */;
/*!40000 ALTER TABLE `report_runs` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-02 17:09:27
