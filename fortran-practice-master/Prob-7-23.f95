subroutine derivative(vector, deriv, nsamp, dx, error)
    integer, intent(in) :: nsamp
    real, intent(in) :: vector(nsamp)
    real, intent(out) :: deriv(nsamp - 1)
    real, intent(in) :: dx 
    integer, intent(out) :: error

    integer :: i 

    if (dx > 0.0) then 
        do i = 1, nsamp - 1 
            deriv(i) = ( vector(i + 1) - vector(i) ) / dx 
        end do 

        error = 0 
    else 
        error = 1
    end if 
    
end subroutine derivative

program test_derivative
    implicit none
    
    ! List of local constants
    integer, parameter :: NSAMP = 100 
    real, parameter :: DX = 0.05

    ! List of local variables
    real, dimension(NSAMP-1) :: cderiv, deriv 
    integer :: error, i 
    real :: max_error 
    real, dimension(NSAMP) :: vector 

    do i = 1, NSAMP 
        vector(i) = sin(real(i-1) * DX)
    end do 

    ! Calculate analytic derivative of f(x)
    do i = 1, NSAMP - 1
        cderiv(i) = cos(real(i-1) * DX)
    end do 

    ! Call *derivative* 
    call derivative(vector, deriv, NSAMP, DX, error)

    ! Find the largest difference 
    max_error = maxval(abs(deriv - cderiv))

    ! Tell user 
    write (*, 1000) max_error
    1000 format(' The maximum error in the derivative is ', F10.4, '.')
end program test_derivative