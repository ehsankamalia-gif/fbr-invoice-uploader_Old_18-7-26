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
-- Table structure for table `excise_owners`
--

DROP TABLE IF EXISTS `excise_owners`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `excise_owners` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `father_name` varchar(100) DEFAULT NULL,
  `cnic` varchar(20) DEFAULT NULL,
  `address` varchar(255) DEFAULT NULL,
  `city` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_excise_owners_cnic` (`cnic`),
  KEY `ix_excise_owners_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `excise_owners`
--

LOCK TABLES `excise_owners` WRITE;
/*!40000 ALTER TABLE `excise_owners` DISABLE KEYS */;
/*!40000 ALTER TABLE `excise_owners` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `excise_payments`
--

DROP TABLE IF EXISTS `excise_payments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `excise_payments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `amount` float NOT NULL,
  `payment_date` date DEFAULT NULL,
  `challan_number` varchar(50) DEFAULT NULL,
  `payment_type` varchar(50) DEFAULT NULL,
  `registration_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `registration_id` (`registration_id`),
  KEY `ix_excise_payments_id` (`id`),
  CONSTRAINT `excise_payments_ibfk_1` FOREIGN KEY (`registration_id`) REFERENCES `excise_registrations` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `excise_payments`
--

LOCK TABLES `excise_payments` WRITE;
/*!40000 ALTER TABLE `excise_payments` DISABLE KEYS */;
/*!40000 ALTER TABLE `excise_payments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `excise_registrations`
--

DROP TABLE IF EXISTS `excise_registrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `excise_registrations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `registration_number` varchar(20) NOT NULL,
  `registration_date` date DEFAULT NULL,
  `token_tax_paid_upto` date DEFAULT NULL,
  `owner_id` int DEFAULT NULL,
  `vehicle_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_excise_registrations_registration_number` (`registration_number`),
  KEY `owner_id` (`owner_id`),
  KEY `vehicle_id` (`vehicle_id`),
  KEY `ix_excise_registrations_id` (`id`),
  CONSTRAINT `excise_registrations_ibfk_1` FOREIGN KEY (`owner_id`) REFERENCES `excise_owners` (`id`),
  CONSTRAINT `excise_registrations_ibfk_2` FOREIGN KEY (`vehicle_id`) REFERENCES `excise_vehicles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `excise_registrations`
--

LOCK TABLES `excise_registrations` WRITE;
/*!40000 ALTER TABLE `excise_registrations` DISABLE KEYS */;
/*!40000 ALTER TABLE `excise_registrations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `excise_vehicles`
--

DROP TABLE IF EXISTS `excise_vehicles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `excise_vehicles` (
  `id` int NOT NULL AUTO_INCREMENT,
  `chassis_number` varchar(50) NOT NULL,
  `engine_number` varchar(50) NOT NULL,
  `make` varchar(50) DEFAULT NULL,
  `model` varchar(50) DEFAULT NULL,
  `year` int DEFAULT NULL,
  `color` varchar(30) DEFAULT NULL,
  `horsepower` varchar(20) DEFAULT NULL,
  `seating_capacity` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_excise_vehicles_chassis_number` (`chassis_number`),
  KEY `ix_excise_vehicles_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `excise_vehicles`
--

LOCK TABLES `excise_vehicles` WRITE;
/*!40000 ALTER TABLE `excise_vehicles` DISABLE KEYS */;
/*!40000 ALTER TABLE `excise_vehicles` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-02 13:08:40
