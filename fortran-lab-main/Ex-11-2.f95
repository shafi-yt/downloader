SUBROUTINE dsimul ( a, b, soln, ndim, n, error )
    !
    ! Purpose:
    ! Subroutine to solve a set of N linear equations in N
    ! unknowns using Gaussian elimination and the maximum
    ! pivot technique. This version of simul has been
    ! modified to use array sections and automatic arrays.
    ! It uses double precision arithmetic to avoid
    ! cumulative roundoff errors. It DOES NOT DESTROY the
    ! original input values.
    !
    ! Record of revisions:
    ! Date       Programmer      Description of change
    ! ====       ==========      =====================
    ! 11/25/15   S. J. Chapman   Original code
    ! 1. 11/25/15 S. J. Chapman  Add automatic arrays
    ! 2. 12/01/15 S. J. Chapman  Double precision
    !
    USE iso_Fortran_env
    IMPLICIT NONE

    ! Data dictionary: declare constants
    REAL(KIND=REAL64), PARAMETER :: EPSILON = 1.0E-12
    ! A "small" number for comparison
    ! when determining singular eqns

    ! Data dictionary: declare calling parameter types & definitions
    INTEGER, INTENT(IN) :: ndim ! Dimension of arrays a and b
    REAL(KIND=REAL64), INTENT(IN), DIMENSION(ndim,ndim) :: a
    ! Array of coefficients (N x N).
    ! This array is of size ndim x
    ! ndim, but only N x N of the
    ! coefficients are being used.
    REAL(KIND=REAL64), INTENT(IN), DIMENSION(ndim) :: b
    ! Input: Right-hand side of eqns.
    REAL(KIND=REAL64), INTENT(OUT), DIMENSION(ndim) :: soln
    ! Output: Solution vector.
    INTEGER, INTENT(IN) :: n                        ! Number of equations to solve.
    INTEGER, INTENT(OUT) :: error                   ! Error flag:
    ! 0 -- No error
    ! 1 -- Singular equations

    ! Data dictionary: declare local variable types & definitions
    REAL(KIND=REAL64), DIMENSION(n,n) :: a1         ! Copy of "a" which will be
    ! destroyed during the solution
    REAL(KIND=REAL64) :: factor                     ! Factor to multiply eqn irow by
    ! before adding to eqn jrow
    INTEGER :: irow                                 ! Number of the equation currently
    ! currently being processed
    INTEGER :: ipeak                                ! Pointer to equation containing
    ! maximum pivot value
    INTEGER :: jrow                                 ! Number of the equation compared
    ! to the current equation
    REAL(KIND=REAL64) :: temp                       ! Scratch value
    REAL(KIND=REAL64),DIMENSION(n) :: temp1         ! Scratch array

    ! Make copies of arrays "a" and "b" for local use
    a1 = a(1:n,1:n)
    soln = b(1:n)

    ! Process N times to get all equations...
    mainloop: DO irow = 1, n
        ! Find peak pivot for column irow in rows irow to N
        ipeak = irow
        max_pivot: DO jrow = irow+1, n
            IF (ABS(a1(jrow,irow)) > ABS(a1(ipeak,irow))) THEN
                ipeak = jrow
            END IF
        END DO max_pivot

        ! Check for singular equations.
        singular: IF ( ABS(a1(ipeak,irow)) < EPSILON ) THEN
            error = 1
            RETURN
        END IF singular

        ! Otherwise, if ipeak /= irow, swap equations irow & ipeak
        swap_eqn: IF ( ipeak /= irow ) THEN
            temp1 = a1(ipeak,1:n) 
            a1(ipeak,1:n) = a1(irow,1:n) ! Swap rows in a
            a1(irow,1:n) = temp1 
            temp = soln(ipeak) 
            soln(ipeak) = soln(irow)     ! Swap rows in b
            soln(irow) = temp 
        END IF swap_eqn

        ! Multiply equation irow by -a1(jrow,irow)/a1(irow,irow),
        ! and add it to Eqn jrow (for all eqns except irow itself).
        eliminate: DO jrow = 1, n
            IF ( jrow /= irow ) THEN
                factor = -a1(jrow,irow)/a1(irow,irow)
                a1(jrow,1:n) = a1(irow,1:n)*factor + a1(jrow,1:n)
                soln(jrow) = soln(irow)*factor + soln(jrow)
            END IF
        END DO eliminate
    END DO mainloop

    ! End of main loop over all equations. All off-diagonal
    ! terms are now zero. To get the final answer, we must
    ! divide each equation by the coefficient of its on-diagonal
    ! term.
    divide: DO irow = 1, n
        soln(irow) = soln(irow) / a1(irow,irow)
    END DO divide

    ! Set error flag to 0 and return.
    error = 0
END SUBROUTINE dsimul

SUBROUTINE simul ( a, b, soln, ndim, n, error )
    !
    ! Purpose:
    ! Subroutine to solve a set of N linear equations in N
    ! unknowns using Gaussian elimination and the maximum
    ! pivot technique. This is the single precision version.
    !
    USE iso_Fortran_env
    IMPLICIT NONE

    ! Data dictionary: declare constants
    REAL(KIND=REAL32), PARAMETER :: EPSILON = 1.0E-6
    ! A "small" number for comparison
    ! when determining singular eqns

    ! Data dictionary: declare calling parameter types & definitions
    INTEGER, INTENT(IN) :: ndim ! Dimension of arrays a and b
    REAL(KIND=REAL32), INTENT(IN), DIMENSION(ndim,ndim) :: a
    ! Array of coefficients (N x N).
    REAL(KIND=REAL32), INTENT(IN), DIMENSION(ndim) :: b
    ! Input: Right-hand side of eqns.
    REAL(KIND=REAL32), INTENT(OUT), DIMENSION(ndim) :: soln
    ! Output: Solution vector.
    INTEGER, INTENT(IN) :: n                        ! Number of equations to solve.
    INTEGER, INTENT(OUT) :: error                   ! Error flag:
    ! 0 -- No error
    ! 1 -- Singular equations

    ! Data dictionary: declare local variable types & definitions
    REAL(KIND=REAL32), DIMENSION(n,n) :: a1         ! Copy of "a" which will be
    ! destroyed during the solution
    REAL(KIND=REAL32) :: factor                     ! Factor to multiply eqn irow by
    INTEGER :: irow                                 ! Number of the equation currently
    INTEGER :: ipeak                                ! Pointer to equation containing
    INTEGER :: jrow                                 ! Number of the equation compared
    REAL(KIND=REAL32) :: temp                       ! Scratch value
    REAL(KIND=REAL32),DIMENSION(n) :: temp1         ! Scratch array

    ! Make copies of arrays "a" and "b" for local use
    a1 = a(1:n,1:n)
    soln = b(1:n)

    ! Process N times to get all equations...
    mainloop: DO irow = 1, n
        ! Find peak pivot for column irow in rows irow to N
        ipeak = irow
        max_pivot: DO jrow = irow+1, n
            IF (ABS(a1(jrow,irow)) > ABS(a1(ipeak,irow))) THEN
                ipeak = jrow
            END IF
        END DO max_pivot

        ! Check for singular equations.
        singular: IF ( ABS(a1(ipeak,irow)) < EPSILON ) THEN
            error = 1
            RETURN
        END IF singular

        ! Otherwise, if ipeak /= irow, swap equations irow & ipeak
        swap_eqn: IF ( ipeak /= irow ) THEN
            temp1 = a1(ipeak,1:n)
            a1(ipeak,1:n) = a1(irow,1:n)
            a1(irow,1:n) = temp1
            temp = soln(ipeak)
            soln(ipeak) = soln(irow)
            soln(irow) = temp
        END IF swap_eqn

        ! Multiply equation irow by -a1(jrow,irow)/a1(irow,irow),
        ! and add it to Eqn jrow (for all eqns except irow itself).
        eliminate: DO jrow = 1, n
            IF ( jrow /= irow ) THEN
                factor = -a1(jrow,irow)/a1(irow,irow)
                a1(jrow,1:n) = a1(irow,1:n)*factor + a1(jrow,1:n)
                soln(jrow) = soln(irow)*factor + soln(jrow)
            END IF
        END DO eliminate
    END DO mainloop

    ! End of main loop over all equations. All off-diagonal
    ! terms are now zero. To get the final answer, we must
    ! divide each equation by the coefficient of its on-diagonal
    ! term.
    divide: DO irow = 1, n
        soln(irow) = soln(irow) / a1(irow,irow)
    END DO divide

    ! Set error flag to 0 and return.
    error = 0
END SUBROUTINE simul

PROGRAM test_dsimul
    !
    ! Purpose:
    ! To test subroutine dsimul, which solves a set of N linear
    ! equations in N unknowns. This test driver calls subroutine
    ! simul to solve the problem in single precision, and subrou-
    ! tine dsimul to solve the problem in double precision. The
    ! results of the two solutions together with their errors are
    ! displayed in a summary table.
    ! Record of revisions:
    ! Date       Programmer      Description of change
    ! ====       ==========      =====================
    ! 12/01/15   S. J. Chapman   Original code
    !
    USE iso_Fortran_env
    IMPLICIT NONE

    ! List of local variables
    REAL(KIND=REAL32), ALLOCATABLE, DIMENSION(:,:) :: a
    ! Single-precision coefficients
    REAL(KIND=REAL32), ALLOCATABLE, DIMENSION(:) :: b
    ! Single-precision constant values
    REAL(KIND=REAL32), ALLOCATABLE, DIMENSION(:) :: soln
    ! Single-precision solution
    REAL(KIND=REAL32), ALLOCATABLE, DIMENSION(:) :: serror
    ! Array of single-precision errors
    REAL(KIND=REAL32) :: serror_max                 ! Max single precision error
    REAL(KIND=REAL64), ALLOCATABLE, DIMENSION(:,:) :: da
    ! Double-precision coefficients
    REAL(KIND=REAL64), ALLOCATABLE, DIMENSION(:) :: db
    ! Double-precision constant values
    REAL(KIND=REAL64), ALLOCATABLE, DIMENSION(:) :: dsoln
    ! Double-precision solution
    REAL(KIND=REAL64), ALLOCATABLE, DIMENSION(:) :: derror
    ! Array of double-precision errors
    REAL(KIND=REAL64) :: derror_max                 ! Max double precision error
    INTEGER :: error_flag                           ! Error flag from subroutines
    INTEGER :: i, j                                 ! Loop index
    INTEGER :: istat                                ! I/O status
    CHARACTER(len=80) :: msg                        ! Error message
    INTEGER :: n                                    ! Size of system of eqns to solve
    CHARACTER(len=20) :: filename                   ! Input data file name

    ! Get the name of the disk file containing the equations.
    WRITE (*,*) 'Enter the file name containing the eqns: '
    READ (*,'(A20)') filename

    ! Open input data file. Status is OLD because the input data must
    ! already exist.
    OPEN ( UNIT=1, FILE=filename, STATUS='OLD', ACTION='READ', &
           IOSTAT=istat, IOMSG=msg )

    ! Was the OPEN successful?
    open_ok: IF ( istat == 0 ) THEN
        ! The file was opened successfully, so read the number of
        ! equations in the system.
        READ (1,*) n

        ! Allocate memory for that number of equations
        ALLOCATE ( a(n,n), b(n), soln(n), serror(n), &
                   da(n,n), db(n), dsoln(n), derror(n), STAT=istat )

        ! If the memory is available, read in equations and
        ! process them.
        solve: IF ( istat == 0 ) THEN
            DO i = 1, n
                READ (1,*) (da(i,j), j=1,n), db(i)
            END DO

            ! Copy the coefficients in single precision for the
            ! single precision solution. Use explicit conversion
            ! to acknowledge potential precision loss
            a = REAL(da, KIND=REAL32)
            b = REAL(db, KIND=REAL32)

            ! Display coefficients.
            WRITE (*,1010)
            1010 FORMAT (/,'Coefficients:')
            DO i = 1, n
                WRITE (*,'(7F11.4)') (a(i,j), j=1,n), b(i)
            END DO

            ! Solve equations.
            CALL simul (a, b, soln, n, n, error_flag )
            CALL dsimul (da, db, dsoln, n, n, error_flag )

            ! Check for error.
            error_check: IF ( error_flag /= 0 ) THEN
                WRITE (*,1020)
                1020 FORMAT (/,'Zero pivot encountered!', &
                         //,'There is no unique solution to this system.')
            ELSE error_check
                ! No errors. Check for roundoff by substituting into
                ! the original equations, and calculate the differences.
                serror_max = 0.
                derror_max = 0._REAL64
                serror = 0.
                derror = 0._REAL64
                DO i = 1, n
                    serror(i) = SUM ( a(i,:) * soln(:) ) - b(i)
                    derror(i) = SUM ( da(i,:) * dsoln(:) ) - db(i)
                END DO
                serror_max = MAXVAL ( ABS ( serror ) )
                derror_max = MAXVAL ( ABS ( derror ) )

                ! Tell user about it.
                WRITE (*,1030)
                1030 FORMAT (/,' i   SP x(i)        DP x(i)       ', &
                               '  SP Err        DP Err      ')
                WRITE (*,1040)
                1040 FORMAT ( ' === ============== ============== ', &
                               ' ============== ============== ')

                DO i = 1, n
                    WRITE (*,1050) i, soln(i), dsoln(i), serror(i), derror(i)
                    1050 FORMAT (I3, 2X, G15.6, G15.6, F15.8, F15.8)
                END DO

                ! Write maximum errors.
                WRITE (*,1060) serror_max, derror_max
                1060 FORMAT (/,'Max single-precision error:',F15.8, &
                               /,'Max double-precision error:',F15.8)
            END IF error_check
        END IF solve

        ! Deallocate dynamic memory
        DEALLOCATE ( a, b, soln, serror, da, db, dsoln, derror )

    ELSE open_ok
        ! Else file open failed. Tell user.
        WRITE (*,1070) filename
        1070 FORMAT ('ERROR: File ',A,' could not be opened!')
        WRITE (*,'(A)') TRIM(msg)
    END IF open_ok
END PROGRAM test_dsimul