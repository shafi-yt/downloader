subroutine lsq_fit_corr_coeff(x, y, nsamp, slope, y_inter, corr_coeff)
    implicit none 
    integer, intent(in) :: nsamp
    real, dimension(nsamp), intent(in) :: x, y
    real, intent(out) :: slope, y_inter, corr_coeff

    ! Define local variable
    integer :: i 
    real :: sum_x = 0., sum_x2 = 0., sum_y = 0., sum_y2 = 0., &
            sum_xy = 0., x_bar, y_bar
    
    do i = 1, nsamp 
        sum_x = sum_x + x(i)
        sum_x2 = sum_x2 + x(i)**2
        sum_y = sum_y + y(i)
        sum_y2 = sum_y2 + y(i)**2 
        sum_xy = sum_xy + x(i)*y(i)
    end do 

    ! Calculate slope, y_intecept, and corelation coefficient
    x_bar = sum_x / real(nsamp)
    y_bar = sum_y / real(nsamp)
    slope = (sum_xy - sum_x*y_bar) / (sum_x2 - sum_x*x_bar)
    y_inter = y_bar - slope * x_bar
    corr_coeff = (nsamp*sum_xy - sum_x*sum_y) / sqrt((nsamp*sum_x2 - sum_x**2)*(nsamp*sum_y2 - sum_y**2))

end subroutine lsq_fit_corr_coeff

program lsq_fit
    implicit none
    integer, parameter :: NSAMP = 100 
    real, dimension(NSAMP) :: x, y 
    real :: slope, y_intecept, corr_coeff
    real :: temp_x, temp_y 
    integer :: iostat, n = 0
    character(len=24) :: filename 

    ! Read filename
    write(*, 1000) 
    1000 format(1x, 'This program calculate the least square fit and ',/, &
                1x, 'correlation coefficient of given data set (x, y).',/, &
                1x, 'Enter the filename which contain the input data set : ')
    read (*,*) filename

    ! Open input file
    open(unit=10, file=filename, status='OLD', action='READ', iostat=iostat)

    ! If opened correctly read the data 
    if (iostat /= 0) then
        write (*,*) 'Error opening file. iostat = ', iostat
        stop
    else 
        do
            read (10,*, iostat=iostat) temp_x, temp_y
            if (iostat /= 0) then 
                write (*,'(/A/)') ' End of file encountered.'
                exit
            else 
                n = n + 1
                x(n) = temp_x
                y(n) = temp_y
            end if 
        end do 
    end if 
    call lsq_fit_corr_coeff(x, y, n, slope, y_intecept, corr_coeff)

    write (*,1010) slope, y_intecept, corr_coeff
    1010 format(1x, 'Slope (m)                  = ',F10.3,/, &
                    'y intercept (b)            = ',F10.3,/, &
                    'corelation coefficient (r) = ',F10.3)

end program lsq_fit