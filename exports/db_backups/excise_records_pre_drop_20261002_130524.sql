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
-- Table structure for table `excise_records`
--

DROP TABLE IF EXISTS `excise_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `excise_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `record_number` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `chassis_number` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `engine_number` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `motorcycle_model` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `color` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `year_of_manufacture` int DEFAULT NULL,
  `customer_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `customer_cnic` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `customer_father_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `customer_phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `customer_address` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `registration_number` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `tax_amount` float DEFAULT NULL,
  `fine_amount` float DEFAULT NULL,
  `total_amount` float DEFAULT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `notes` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `is_deleted` tinyint(1) DEFAULT NULL,
  `attachments` json DEFAULT NULL,
  `maker_make` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `amount` float DEFAULT NULL,
  `income` float DEFAULT NULL,
  `profit` float DEFAULT NULL,
  `income2` float DEFAULT NULL,
  `expenditure` float DEFAULT NULL,
  `tcs_receiving_date` datetime DEFAULT NULL,
  `excise_submitting_date` datetime DEFAULT NULL,
  `dealer_address` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `issue_authority` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `receiver` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `file_card` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `modified_pc` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `remarks` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `company_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_company_excise_record_number` (`company_id`,`record_number`),
  UNIQUE KEY `uq_company_excise_chassis` (`company_id`,`chassis_number`),
  UNIQUE KEY `uq_company_excise_engine` (`company_id`,`engine_number`),
  KEY `ix_excise_records_status` (`status`),
  KEY `ix_excise_records_customer_cnic` (`customer_cnic`),
  KEY `ix_excise_records_is_deleted` (`is_deleted`),
  KEY `ix_excise_records_id` (`id`),
  KEY `ix_excise_records_registration_number` (`registration_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `excise_records`
--

LOCK TABLES `excise_records` WRITE;
/*!40000 ALTER TABLE `excise_records` DISABLE KEYS */;
/*!40000 ALTER TABLE `excise_records` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-02 13:05:24
