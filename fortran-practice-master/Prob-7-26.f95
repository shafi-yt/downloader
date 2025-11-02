subroutine lsq_fit(x, y, nsamp, slope, y_inter)
    implicit none

    integer, intent(in) :: nsamp 
    real, intent(in) :: x(nsamp), y(nsamp)
    real, intent(out) :: slope, y_inter

    real :: sum_x = 0., sum_x2 = 0., sum_y = 0., &
             sum_y2 = 0., sum_xy = 0., x_bar, y_bar
    integer :: i 

    do i = 1, nsamp
        sum_x = sum_x + x(i) 
        sum_y = sum_y + y(i)
        sum_x2 = sum_x2 + x(i)**2 
        sum_y2 = sum_y2 + y(i)**2
        sum_xy = sum_xy + x(i)*y(i) 
    end do 

    x_bar = sum_x / nsamp 
    y_bar = sum_y / nsamp 

    slope = ((sum_xy) - (sum_x*y_bar)) / (sum_x2 - (sum_x*x_bar))
    y_inter = y_bar - slope * x_bar
end subroutine lsq_fit


program test_lsq
    implicit none 
    integer, parameter :: nsamp = 20 
    real :: x(nsamp), y(nsamp)
    real :: slope, y_inter

    x = [-4.91, -3.84, -2.41, -2.62, -3.78, -0.52, -1.83, -2.01, &
    0.28, 1.08, -0.94, 0.59, 0.69, 3.04, 1.01, 3.60, 4.53, 5.13, 4.43, 4.12]

    y = [-8.18, -7.49, -7.11, -6.15, -5.62, -3.30, -2.05, -2.83, -1.16, 0.52, &
    0.21, 1.73, 3.69, 4.26, 5.75, 6.67, 7.70, 7.31, 9.05, 10.95]

    call lsq_fit(x, y, nsamp, slope, y_inter)

    write (*,100) slope, y_inter, nsamp
    100 format(1x,'Regression coeffieients for teh least-squares line: ',/, &
            ' slope (m)     = ', f10.3, /, &
            ' intercept (b) = ', f10.3,/, &
            ' no of samples = ', i10)
end program test_lsq