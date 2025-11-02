program all_means
    implicit none
    integer :: n = 0, iostat
    real :: ave, g_mean, h_mean, rms 
    real :: prod_x = 1.0
    real :: sum_x = 0.0 
    real :: sum_x2 = 0.0
    real :: sum_rx = 0.0 
    real :: x = 0.0
    character(len=20) :: input_file 
    character(len=100) :: iomsg

    write (*,1010) 
    1010 format(1x, 'This program calculates the average (arithmetic mean), ',/, &
                1x, 'geometric mean, harmonic mean, and rms average of an ',/, &
                1x, 'input data set. Enter name of file containing the ',/, &
                1x, 'input data: ')
    read (*,'(A)') input_file 

    open(unit=10, file=input_file, status='old', iostat=iostat, iomsg=iomsg)

    if (iostat > 0) then
        write (*, 1020) input_file, iostat, trim(iomsg)
    1020 format(1x, 'Error opening input file ', A, &
                 ', iostat = ', I0, ', message: ', A)
    else 
        do 
            read (10, *, iostat=iostat) x 
            if (iostat /= 0) exit 
            n = n + 1 
            prod_x = prod_x * x 
            sum_x = sum_x + x 
            sum_x2 = sum_x2 + x**2 
            sum_rx = sum_rx + 1.0 / x 
        end do 

        ave = sum_x / real(n) 
        g_mean = prod_x**(1.0 / real(n)) 
        h_mean = real(n) / sum_rx 
        rms = sqrt(sum_x2 /real(n)) 
        write (*,1030) n, ave, g_mean, h_mean, rms
    1030 format(1x, 'Number of data points: ', I0, /, &
                 1x, 'Arithmetic mean: ', F12.4, /, &
                 1x, 'Geometric mean: ', F12.4, /, &
                 1x, 'Harmonic mean: ', F12.4, /, &
                 1x, 'RMS average: ', F12.4)
    end if
end program all_means