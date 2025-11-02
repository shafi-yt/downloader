program lsq_corr_coeff
    implicit none

    integer :: n = 0, iostat 
    real :: sum_x = 0.0, sum_y = 0.0, sum_xy = 0.0
    real :: sum_x2 = 0.0, sum_y2 = 0.0 
    real :: x, y, x_bar, y_bar
    real :: slope, y_int, correl 
    character(len=20) :: filename 
    
    ! Prompt user for input file name 
    write (*, 1000)
    1000 format('This program performs a least-squares fit of an ',/, &
                ' input data set to a straight line. It also ',/, &
                ' calculates the correlation coefficient of the fit. ',/, &
                ' Enter the name of the file containing the input', &
                ' (x, y) pairs: ')

    read (*, '(A)') filename 
    
    open (unit=10, file=filename, status='old', iostat=iostat) 

    if (iostat > 0) then
        write (*, 1010) filename 
        1010 format(1x, 'ERROR: File ', A, ' does not exists!')
    else 
        ! Read data points from file and accumulate sums 
        do 
            read (10, *, iostat=iostat) x, y 
            if (iostat /= 0) exit 
            n = n + 1 
            sum_x = sum_x + x
            sum_y = sum_y + y 
            sum_x2 = sum_x2 + x**2 
            sum_y2 = sum_y2 + y**2 
            sum_xy = sum_xy + x * y 
        end do 
        
        if (n > 1) then 
            x_bar = sum_x / n 
            y_bar = sum_y / n 
            slope = (sum_xy - sum_x * y_bar) / (sum_x2 - sum_x * x_bar) 
            y_int = y_bar - slope * x_bar 

            ! Calculate correlation coefficient 
            correl = ( real(n) * sum_xy - - sum_x * sum_y ) / &
                        sqrt((real(n) * sum_x2 - sum_x**2) * (real(n) * sum_y2 - sum_y**2)) 
            
            ! Output results 
            write (*, 1020) slope, y_int, correl, n 
            1020 format(1x, 'Regression coefficients for the least-squares line:', &
                        /,1x, 'Slope (m)                   = ', F12.3, &
                        /,1x, 'Y-Intercept (b)             = ', F12.3, &
                        /,1x, 'Correlation Coefficient (r) = ', F12.3, &
                        /,1x, 'No of points                = ', I12)
            if (abs(correl) < 0.3) then
                write (*, 1030) 
                1030 format(1x,'WARNING: Small correlation coefficient!')
            end if 

        else 
            write (*, 1040) 
            1040 format(1x, 'ERROR: Not enough data points to perform regression!')
        end if 

        close(10)
    end if 
end program lsq_corr_coeff