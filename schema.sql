-- Delete existing tables to ensure a clean slate
DROP TABLE IF EXISTS attendance;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS teachers;
DROP TABLE IF EXISTS classes;
DROP TABLE IF EXISTS admins;

-- Table for Admins
CREATE TABLE admins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL
);

-- Table for Classes (e.g., "Grade 10A", "Physics 101")
CREATE TABLE classes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

-- Table for Teachers
CREATE TABLE teachers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  phone TEXT,
  password TEXT NOT NULL,
  class_id INTEGER,
  is_approved BOOLEAN NOT NULL DEFAULT 0, -- 0 for false, 1 for true
  FOREIGN KEY (class_id) REFERENCES classes(id)
);

-- Table for Students
CREATE TABLE students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  username TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL,
  class_id INTEGER NOT NULL,
  FOREIGN KEY (class_id) REFERENCES classes(id)
);

-- Table for Attendance Records
CREATE TABLE attendance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  date TEXT NOT NULL,
  status TEXT NOT NULL, -- e.g., "Full Day", "Half Day", "Absent"
  remarks TEXT,
  UNIQUE(student_id, date),
  FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

