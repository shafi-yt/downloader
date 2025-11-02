program calc_dot_products
    implicit none
    integer, parameter :: SIZE = 3
    real, dimension(SIZE) :: vec1, vec2
    real :: dot_products 

    ! Get the first vector 
    write (*, 1000)
    1000 format(' Calculate the dot product of 2 vectors. ', &
                /,1x,'Enter first vector (three terms): ')
    read (*,*) vec1 

    ! Get the second vector 
    write (*, 1010) 
    1010 format(1x, ' Enter second vector (three terms): ')
    read (*,*) vec2 

    ! Calculate the dot product of the two vectors 
    dot_products = vec1(1) * vec2(1) + vec1(2) * vec2(2) + vec1(3) * vec2(3) 

    ! Tell user the result 
    write (*, 1020) dot_products 
    1020 format(1x, ' The dot product is: ', F12.4)

end program calc_dot_products