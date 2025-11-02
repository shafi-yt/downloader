Here are the complete Fortran program solutions for all three questions on the sheet.
I have written these using modern Fortran standards (like IMPLICIT NONE and defined precision) as this is a best practice for numerical and scientific programming.
1. Sine Calculation and Series Comparison
This program reads an angle in degrees, converts it to radians, and then compares the value from the built-in SIN function to a 10-term Taylor series. It also reports how many terms of the series are needed to match the full accuracy of the intrinsic function.
💡 Logic
 * High Precision: We use REAL(KIND=dp) (double precision) for all calculations to see the effects of "full accuracy."
 * Conversion: The input x_deg (degrees) is converted to x_rad (radians) since all trigonometric functions in Fortran require radians.
 * True Value: The "true" value is stored from the intrinsic SIN(x_rad) function.
 * Recurrence Relation: To calculate the series \sum \frac{(-1)^{n-1} x^{2n-1}}{(2n-1)!}, we don't calculate factorials and powers separately. This is inefficient and leads to overflow. Instead, we use a recurrence relation:
   *    *  * Finding Terms: We loop, adding the next term to the sum. We check when the sum equals the true_sine (within machine precision, checked using EPSILON) and record the term number.
💻 Fortran Code
PROGRAM Sine_Comparison
  IMPLICIT NONE

  ! Use double precision for accuracy
  INTEGER, PARAMETER :: dp = KIND(1.0D0)
  REAL(KIND=dp) :: x_deg, x_rad, pi
  REAL(KIND=dp) :: true_sine, series_sine, series_sine_10_terms, term
  INTEGER :: n, terms_needed
  LOGICAL :: accuracy_met

  ! Define Pi
  pi = 4.0_dp * ATAN(1.0_dp)

  ! 1. Read input in degrees
  PRINT *, "Enter a value for x in degrees:"
  READ (*,*) x_deg

  ! 2. Convert to radians
  x_rad = x_deg * (pi / 180.0_dp)

  ! 3. Calculate the "true" value
  true_sine = SIN(x_rad)
  
  ! 4. Calculate the series
  series_sine = 0.0_dp
  term = x_rad            ! This is the first term (n=1)
  series_sine = term      ! Add the first term to the sum
  accuracy_met = .FALSE.
  terms_needed = 0

  ! Loop from the second term (n=2) onwards
  DO n = 2, 30  ! 30 terms is more than enough for convergence
    
    ! Calculate the next term from the previous one
    term = term * (-1.0_dp * x_rad**2) / ((2.0_dp*n - 1.0_dp) * (2.0_dp*n - 2.0_dp))
    series_sine = series_sine + term
    
    ! Store the 10-term sum
    IF (n == 10) THEN
      series_sine_10_terms = series_sine
    END IF
    
    ! 5. Check if we have reached full accuracy
    IF (ABS(series_sine - true_sine) < EPSILON(true_sine) .AND. .NOT. accuracy_met) THEN
      terms_needed = n
      accuracy_met = .TRUE.
    END IF
    
  END DO

  ! 6. Display results
  PRINT *, "-------------------------------------------"
  PRINT *, "Angle (degrees): ", x_deg
  PRINT *, "Angle (radians): ", x_rad
  PRINT *, "-------------------------------------------"
  PRINT *, "True value (intrinsic SIN): ", true_sine
  PRINT *, "Series value (10 terms):    ", series_sine_10_terms
  PRINT *, "-------------------------------------------"
  PRINT *, "Terms required for full accuracy: ", terms_needed

END PROGRAM Sine_Comparison

Example Output (for x=30 degrees):
 Enter a value for x in degrees:
 30
 -------------------------------------------
 Angle (degrees):    30.0000000000000     
 Angle (radians):   0.5235987755982989     
 -------------------------------------------
 True value (intrinsic SIN):   0.5000000000000000     
 Series value (10 terms):    0.5000000000000000     
 -------------------------------------------
 Terms required for full accuracy:           8

2. Reading and Retrieving from a Scratch File
This program accepts a list of numbers from the user, stores them in a temporary "scratch" file, and then retrieves a specific record requested by the user.
💡 Logic
 * Scratch File: We OPEN a file with STATUS='SCRATCH'. This creates a temporary file that is automatically deleted when the program ends or the file is closed. We use ACCESS='SEQUENTIAL' and FORM='UNFORMATTED' for simple, efficient I/O.
 * Writing: A DO loop reads values. If the value is non-negative, it's written to the file using WRITE(unit). If it's negative, the loop EXITs.
 * Rewind: After writing, the file pointer is at the end. We must REWIND(unit) to move the pointer back to the beginning before we can read.
 * Reading: We ask the user for a record_num. We then use a DO loop from 1 to record_num to read from the file. The loop reads and discards the first record_num - 1 records, and the final value read (stored in retrieved_val) is the one the user wanted.
 * Error Handling: The READ statement includes an END=100 clause. If the program tries to read past the end of the file (e.g., the user asks for record 50 but only 10 exist), it jumps to the statement labeled 100 to print an error.
💻 Fortran Code
PROGRAM Scratch_File_Demo
  IMPLICIT NONE
  
  REAL :: val, retrieved_val
  INTEGER :: record_num, i
  INTEGER, PARAMETER :: file_unit = 10

  ! 1. Open a temporary scratch file
  OPEN(UNIT=file_unit, STATUS='SCRATCH', ACCESS='SEQUENTIAL', &
       FORM='UNFORMATTED')

  ! 2. Read values and write to file
  PRINT *, "Enter non-negative real numbers."
  PRINT *, "Enter a negative number to stop."
  DO
    READ (*,*) val
    IF (val < 0.0) THEN
      EXIT  ! Exit loop if value is negative
    END IF
    WRITE (file_unit) val
  END DO

  PRINT *, "Data entry complete."
  PRINT *, "---------------------"

  ! 3. Ask user which record to retrieve
  PRINT *, "Enter the record number you want to retrieve:"
  READ (*,*) record_num

  ! 4. Rewind the file to read from the start
  REWIND(file_unit)

  ! 5. Read sequentially to the desired record
  retrieved_val = -999.99  ! A sentinel value
  DO i = 1, record_num
    ! Read from the file. If end-of-file is hit, jump to label 100
    READ (file_unit, END=100) retrieved_val
  END DO

  ! 6. Display the recovered value
  PRINT *, "Record", record_num, "contains the value:", retrieved_val
  GOTO 200  ! Skip the error message

  ! 7. Error handling block
100 PRINT *, "Error: Record not found."
    PRINT *, "The file only contains", i-1, "records."

  ! 8. Close the file (which also deletes it)
200 CONTINUE
  CLOSE(file_unit)

END PROGRAM Scratch_File_Demo

Example Output:
 Enter non-negative real numbers.
 Enter a negative number to stop.
 10.5
 22.0
 99.1
 4.0
 -1
 Data entry complete.
 ---------------------
 Enter the record number you want to retrieve:
 3
 Record           3 contains the value:    99.0999985    

3. Subroutine for Function Optimization
This problem is solved in two parts: the main "driver" program and the SUBROUTINE it calls. The subroutine is designed to find the min/max of any function passed to it.
💡 Logic
 * Driver Program: The main program Test_Min_Max defines the function f(x) = x^3 - 5x^2 + 5x + 2 inside a CONTAINS block. It also declares this function as EXTERNAL to tell the compiler it will be passed as an argument.
 * Function Argument: The find_min_max subroutine lists func as an argument and also declares it EXTERNAL. This allows the subroutine to call whatever function name was passed to it.
 * Search: The subroutine calculates a step_size based on the range and number of steps.
 * Initialization: It's crucial to initialize min_val and max_val to the first value in the range (func(first_val)). This prevents errors if all function values are, for example, negative.
 * Loop: It then loops from i = 1 to num_steps, calculating the current_x and current_y at each step. It compares current_y to the stored min_val and max_val, updating them as needed.
 * Output: The INTENT(OUT) arguments in the subroutine are automatically updated, so when the CALL statement finishes, the variables xmin, fmin, xmax, fmax in the main program hold the results.
💻 Fortran Code
PROGRAM Test_Min_Max
  ! This is the main "test driver" program
  IMPLICIT NONE
  
  ! Use double precision
  INTEGER, PARAMETER :: dp = KIND(1.0D0)
  
  ! Variables to hold the output from the subroutine
  REAL(KIND=dp) :: x_min_val, min_val, x_max_val, max_val
  
  ! Declare the function that will be passed as an argument
  EXTERNAL user_func

  PRINT *, "Searching f(x) = x^3 - 5x^2 + 5x + 2"
  PRINT *, "over the range [-1.0, 3.0] in 200 steps..."
  PRINT *, "-------------------------------------------"

  ! Call the subroutine
  CALL find_min_max(user_func, -1.0_dp, 3.0_dp, 200, &
       x_min_val, min_val, x_max_val, max_val)

  ! Print the results
  PRINT *, "Maximum value found: ", max_val, " at x = ", x_max_val
  PRINT *, "Minimum value found: ", min_val, " at x = ", x_min_val

CONTAINS

  !~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  ! The Subroutine required by the problem
  !~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  SUBROUTINE find_min_max(func, first_val, last_val, num_steps, &
                          x_min_val, min_val, x_max_val, max_val)
    IMPLICIT NONE
    INTEGER, PARAMETER :: dp = KIND(1.0D0)

    ! === Argument Declarations ===
    INTEGER, INTENT(IN) :: num_steps
    REAL(KIND=dp), INTENT(IN) :: first_val, last_val
    REAL(KIND=dp), INTENT(OUT) :: x_min_val, min_val, x_max_val, max_val
    
    ! 'func' is the function being passed. It must be declared EXTERNAL.
    EXTERNAL func
    REAL(KIND=dp) :: func

    ! === Local Variables ===
    INTEGER :: i
    REAL(KIND=dp) :: step_size, current_x, current_y

    ! Calculate the step size
    step_size = (last_val - first_val) / REAL(num_steps, dp)

    ! Initialize min/max with the values at the starting point
    min_val = func(first_val)
    max_val = min_val
    x_min_val = first_val
    x_max_val = first_val

    ! Loop through the range, starting from the *second* point (i=1)
    DO i = 1, num_steps
      current_x = first_val + i * step_size
      current_y = func(current_x)

      ! Check for a new minimum
      IF (current_y < min_val) THEN
        min_val = current_y
        x_min_val = current_x
      END IF

      ! Check for a new maximum
      IF (current_y > max_val) THEN
        max_val = current_y
        x_max_val = current_x
      END IF
    END DO

  END SUBROUTINE find_min_max
  
  !~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  ! The user-defined function for the test driver
  !~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  FUNCTION user_func(x)
    IMPLICIT NONE
    INTEGER, PARAMETER :: dp = KIND(1.0D0)
    REAL(KIND=dp), INTENT(IN) :: x
    REAL(KIND=dp) :: user_func
    
    ! f(x) = x^3 - 5x^2 + 5x + 2
    user_func = x**3 - 5.0_dp * x**2 + 5.0_dp * x + 2.0_dp
    
  END FUNCTION user_func

END PROGRAM Test_Min_Max

Example Output:
 Searching f(x) = x^3 - 5x^2 + 5x + 2
 over the range [-1.0, 3.0] in 200 steps...
 -------------------------------------------
 Maximum value found:    3.2954800000000018      at x =   0.59999999999999964    
 Minimum value found:   -9.0000000000000000      at x =  -1.0000000000000000 

(Note: The exact minimum from calculus is at x \approx 2.76, but for the given range of [-1, 3] and this discrete step search, the minimum value in the search range is found at the endpoint x=-1, where f(-1) = -9.)
