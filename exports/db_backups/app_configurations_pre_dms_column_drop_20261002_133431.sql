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
-- Table structure for table `app_configurations`
--

DROP TABLE IF EXISTS `app_configurations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `app_configurations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `auto_push_enabled` tinyint(1) DEFAULT NULL,
  `auto_push_interval` int DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `address_shortcodes` json DEFAULT NULL,
  `urdu_font_enabled` tinyint(1) DEFAULT '0',
  `urdu_font_family` varchar(200) DEFAULT 'Jameel Noori Nastaleeq',
  `urdu_font_path` varchar(500) DEFAULT '',
  `urdu_font_size` int DEFAULT '14',
  `ui_font_enabled` tinyint(1) DEFAULT '0',
  `ui_font_family` varchar(200) DEFAULT '',
  `ui_font_size` int DEFAULT '13',
  `sidebar_font_size` int DEFAULT '15',
  `sidebar_group_font_size` int DEFAULT '12',
  `sidebar_header_font_size` int DEFAULT '18',
  `sidebar_footer_font_size` int DEFAULT '15',
  `sidebar_exit_font_size` int DEFAULT '16',
  `sidebar_collapsed_font_size` int DEFAULT '18',
  `dms_portal_url` varchar(255) DEFAULT 'https://dms.ahlportal.com/login',
  `dms_username` varchar(100) DEFAULT NULL,
  `dms_password` varchar(100) DEFAULT NULL,
  `invoice_logo_data_url` text,
  `invoice_logo_name` varchar(200) DEFAULT NULL,
  `invoice_font_family` varchar(200) DEFAULT 'Arial, sans-serif',
  `invoice_font_field_size_pt` int DEFAULT '11',
  `invoice_font_label_size_pt` int DEFAULT '9',
  `invoice_font_weight_field` int DEFAULT '600',
  `invoice_font_weight_label` int DEFAULT '500',
  `invoice_business_name_size_pt` int DEFAULT '16',
  `invoice_business_name_weight` int DEFAULT '800',
  `invoice_color_label` varchar(20) DEFAULT '#555555',
  `invoice_mono_font_family` varchar(200) DEFAULT 'Consolas, ''Courier New'', monospace',
  `company_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_app_configurations_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `app_configurations`
--

LOCK TABLES `app_configurations` WRITE;
/*!40000 ALTER TABLE `app_configurations` DISABLE KEYS */;
INSERT INTO `app_configurations` VALUES (1,0,5,'2026-09-27 04:13:49','{\"KT\": \"Tehsil Kamalia District Toba Tek Singh\", \"PT\": \"KAMALA PAKISTAN\"}',0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login','101296-A','RANA@101296','data:image/png;base64,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','download.png','Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',2),(2,0,5,'2026-09-30 19:05:42',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(3,0,5,'2026-09-30 19:05:42',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(4,0,5,'2026-10-01 02:43:58',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(5,0,5,'2026-10-01 02:43:58',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(6,0,5,'2026-10-01 04:01:33',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(7,0,5,'2026-10-01 04:03:22',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(8,0,5,'2026-10-01 04:17:14',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(9,0,5,'2026-10-01 04:17:14',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(10,0,5,'2026-10-01 04:17:30',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(11,0,5,'2026-10-01 04:19:30',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(12,0,5,'2026-10-01 04:20:52',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(13,0,5,'2026-10-01 04:21:40',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(14,0,5,'2026-10-01 04:21:57',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(15,0,5,'2026-10-02 08:06:20',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL),(16,0,5,'2026-10-02 08:06:34',NULL,0,'Jameel Noori Nastaleeq','',14,0,'',13,15,12,18,15,16,18,'https://dms.ahlportal.com/login',NULL,NULL,NULL,NULL,'Arial, sans-serif',11,9,600,500,16,800,'#555555','Consolas, \'Courier New\', monospace',NULL);
/*!40000 ALTER TABLE `app_configurations` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-02 13:34:31
