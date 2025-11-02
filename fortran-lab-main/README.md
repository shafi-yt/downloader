# Fortran Programming Lab Assignments

This repository contains a collection of Fortran programs and subroutines developed as part of a Fortran Programming Lab course. The code demonstrates various numerical algorithms and data structures implemented in Fortran.

## 📁 Repository Structure

The repository includes the following Fortran programs and modules:

### 🧮 Linear Equation Solvers
- **`Ex9-1.f95`** - Gaussian elimination with maximum pivot technique for solving linear equations
- **`Ex-11-2.f95`** - Enhanced version with double precision arithmetic and automatic arrays to minimize roundoff errors

### 🔗 Linked List Programs
- **`Ex-15-1.f95`** - Implementation of a linked list data structure for storing real values
- **`Ex-15-2.f95`** - Insertion sort algorithm using linked lists for integer values

### 📊 Array Operations
- **`Ex-15-3.f95`** - Subroutine to extract diagonal elements from 2D arrays with comprehensive error handling
- **`Ex-12-1.f95`** - Customer database management system with multiple sorting options (by last name, city, or zip code)

### 🌳 Binary Tree Implementation
- **`Ex-15-4.f95`** - Binary tree data structure for storing and retrieving personal information (names, phone numbers) with alphabetical sorting

## 🛠️ Features

### Data Structures
- Dynamic memory allocation with pointers
- Linked lists for sequential data storage
- Binary trees for efficient searching and sorting
- Derived data types for complex data organization

### Numerical Methods
- Gaussian elimination with partial pivoting
- Insertion sort algorithm
- Matrix operations and diagonal extraction
- Single and double precision numerical solvers

### Error Handling
- Comprehensive error checking
- Memory allocation status verification
- Input validation and file operation checks

## 📋 Requirements

- Fortran 90/95 compiler (gfortran, ifort, etc.)
- Basic understanding of Fortran programming
- Input data files for programs that require external data

## 📝 Author

**Shahad Uddin**  
- 🔗 **GitHub**: [shahad-99](https://github.com/shahad-99)    
- 🏫 **Course**: MAT316 FORTRAN PROGRAMMING LAB
- ✔ **Reg No**: 2021133063

## 🚀 Compilation and Execution

### Basic Compilation💢
```bash
gfortran -o program_name program_name.f95
./program_name

# Compile and run linear equation solvers
gfortran -o Ex9-1 Ex9-1.f95
./Ex9-1

gfortran -o Ex-11-2 Ex-11-2.f95
./Ex-11-2

# Compile and run customer database program
gfortran -o Ex-12-1 Ex-12-1.f95
./Ex-12-1

# Compile and run linked list program
gfortran -o Ex-15-1 Ex-15-1.f95
./Ex-15-1

# Compile and run Insertion sort algorithm
gfortran -o Ex-15-2 Ex-15-2.f95
./Ex-15-2

# Compile and run diagonal extraction program
gfortran -o Ex-15-3 Ex-15-3.f95
./Ex-15-3

# Compile and run binary tree program
gfortran -o Ex-15-4 Ex-15-4.f95
./Ex-15-4
